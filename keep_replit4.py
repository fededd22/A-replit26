#!/usr/bin/env python3
"""
سكربت Replit معتمد على cookies.txt الجاهزة
- لا يحاول تسجيل الدخول إطلاقاً
- يستخدم الكوكيز الموجودة مباشرة
- يفتح المشروع + يشغله + يفتح الرابط المستهدف
"""

import os
import sys
import json
import time
import re
import signal
import threading
import http.cookiejar
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ==================== الإعدادات ====================
REPLIT_COOKIE_FILE = "cookies.txt"      # ← ملف الكوكيز الجاهز من متصفحك
REPLIT_PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REPLIT_TARGET_URL = "https://f9732b2f-7002-4f57-b44c-a25d6ab8587c-00-27z973qza9qqb.kirk.replit.dev:443"
REPLIT_REFRESH_INTERVAL = 30

KEEP_ALIVE_PORT = 8080

running = True
last_update_time = None
last_status = "idle"
last_project_opened = False
last_target_opened = False


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ==================== تحميل الكوكيز ====================

def load_cookies(cookie_file):
    """
    تحميل الكوكيز من أي صيغة:
    - Netscape (ملف .txt من إضافات المتصفح)
    - JSON (مصفوفة أو كائن)
    """
    if not os.path.exists(cookie_file):
        log(f"❌ ملف {cookie_file} غير موجود!")
        return []
    
    cookies = []
    
    # ----- 1. جرّب JSON أولاً -----
    try:
        with open(cookie_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        if content.startswith(('[', '{')):
            data = json.loads(content)
            if isinstance(data, dict):
                if 'cookies' in data:
                    data = data['cookies']
                else:
                    data = [data]
            
            for c in data:
                if not isinstance(c, dict):
                    continue
                cookies.append({
                    'name': c.get('name'),
                    'value': c.get('value'),
                    'domain': c.get('domain', '.replit.com'),
                    'path': c.get('path', '/'),
                    'secure': bool(c.get('secure', True)),
                    'httpOnly': bool(c.get('httpOnly', False)),
                    'sameSite': c.get('sameSite', 'Lax') if c.get('sameSite') in ('Strict','Lax','None') else 'Lax',
                    'expires': int(c['expires']) if isinstance(c.get('expires'), (int,float)) and c['expires'] > 0 else None,
                })
            if cookies:
                log(f"✅ تم تحميل {len(cookies)} كوكي (JSON)")
    except Exception as e:
        log(f"⚠️ خطأ JSON: {e}")
    
    # ----- 2. إذا فشل، جرّب Netscape -----
    if not cookies:
        try:
            jar = http.cookiejar.MozillaCookieJar(cookie_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            
            for c in jar:
                entry = {
                    'name': c.name,
                    'value': c.value,
                    'domain': c.domain or '.replit.com',
                    'path': c.path or '/',
                    'secure': bool(c.secure),
                    'httpOnly': bool(c._rest.get('HttpOnly', False)) if hasattr(c, '_rest') else False,
                    'sameSite': 'Lax',
                }
                if c.expires and c.expires > 0:
                    entry['expires'] = int(c.expires)
                cookies.append(entry)
            
            log(f"✅ تم تحميل {len(cookies)} كوكي (Netscape)")
        except Exception as e:
            log(f"❌ فشل Netscape: {e}")
    
    if not cookies:
        return []
    
    # ----- 3. تنظيف: إزالة الحقول None، وإصلاح domains -----
    cleaned = []
    seen = set()
    for c in cookies:
        if not c.get('name') or not c.get('value'):
            continue
        
        # إزالة الـ dot prefix
        c['domain'] = c['domain'].lstrip('.') if c['domain'] else 'replit.com'
        
        # تجنب التكرار
        key = (c['name'], c['domain'], c['path'])
        if key in seen:
            continue
        seen.add(key)
        
        # إزالة None
        c = {k: v for k, v in c.items() if v is not None}
        
        # نفس الموقع
        if 'sameSite' not in c:
            c['sameSite'] = 'Lax'
        
        cleaned.append(c)
    
    # ----- 4. فلترة كوكيز replit فقط (مهم) -----
    replit_cookies = [c for c in cleaned if 'replit' in c['domain'].lower()]
    
    log(f"🍪 كوكيز Replit فقط: {len(replit_cookies)} (من أصل {len(cleaned)})")
    
    # اطبع أسماء أهم الكوكيز للتشخيص
    important_names = {'connect.sid', '__Secure-next-auth.session-token',
                       'replit_session', 'replit_legal_consent', 'sessionId'}
    found = [c['name'] for c in replit_cookies if c['name'] in important_names]
    if found:
        log(f"🔑 كوكيز مهمة موجودة: {found}")
    else:
        log(f"⚠️ لا كوكيز جلسة معروفة! الأسماء: {[c['name'] for c in replit_cookies[:10]]}")
    
    return replit_cookies


# ==================== سياق المتصفح ====================

STEALTH_SCRIPT = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || {};
window.chrome.runtime = window.chrome.runtime || {};
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
    ]
});
"""


def create_context(playwright, cookies):
    """إنشاء سياق مع الكوكيز"""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--window-size=1920,1080',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
        ],
    )
    
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="Asia/Riyadh",
        color_scheme="light",
    )
    
    context.add_init_script(STEALTH_SCRIPT)
    
    # أضف الكوكيز
    if cookies:
        try:
            context.add_cookies(cookies)
            log(f"✅ أُضيفت {len(cookies)} كوكي إلى المتصفح")
        except Exception as e:
            log(f"⚠️ خطأ إضافة الكوكيز: {e}")
            # جرّب واحداً واحداً
            added = 0
            for c in cookies:
                try:
                    context.add_cookies([c])
                    added += 1
                except:
                    continue
            log(f"✅ أُضيف {added}/{len(cookies)} كوكي بشكل فردي")
    
    return browser, context


# ==================== التحقق من الجلسة ====================

def is_logged_in(page) -> bool:
    """تحقق إن كنا مسجلين دخول"""
    try:
        url = page.url
        if '/login' in url or '/signin' in url:
            return False
        
        # ابحث عن علامات وجود الحساب
        indicators = [
            '[data-testid="user-menu"]',
            'button[aria-label*="account" i]',
            'button[aria-label*="profile" i]',
            'button[aria-label*="user" i]',
            'img[alt*="avatar" i]',
            '[class*="avatar"]',
            'a[href="/home"]',
            'a[href*="/@"][class*="user"]',
        ]
        
        for ind in indicators:
            try:
                el = page.locator(ind).first
                if el.count() > 0 and el.is_visible(timeout=1000):
                    return True
            except:
                continue
        
        # إذا وصلنا لـ dashboard/home = مسجل دخول
        if '/home' in url or '/dashboard' in url or '/@' in url:
            return True
        
        return False
    except:
        return False


# ==================== تشغيل المشروع ====================

def click_run_or_workflow(page) -> str:
    log("🔍 البحث عن زر التشغيل...")
    
    # هل يعمل؟
    for ind in [
        'button:has-text("Stop")',
        'iframe[src*="replit.dev"]',
        'iframe[src*="replit.app"]',
        'iframe[src*="kirk.replit.dev"]',
    ]:
        try:
            el = page.locator(ind).first
            if el.count() > 0 and el.is_visible(timeout=800):
                log(f"✅ مؤشر يعمل: {ind}")
                return "running"
        except:
            pass
    
    selectors = [
        'button:has-text("Run")',
        '[role="button"]:has-text("Run")',
        'button:has-text("Start")',
        'button:has-text("Preview")',
        'button[aria-label="Run"]',
        'button[aria-label*="Run" i]',
        'button[aria-label*="Play" i]',
        '[data-testid="run-button"]',
        '[data-testid*="run" i]',
        '[data-testid*="workflow" i]',
        'button:has(svg[viewBox*="play"])',
    ]
    
    for attempt in range(8):
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=1500):
                    el.click()
                    log(f"✅ نقر → {sel}")
                    page.wait_for_timeout(5000)
                    return "clicked"
            except:
                continue
        
        # JS
        try:
            r = page.evaluate("""
                () => {
                    const kws = ['run','start','play','preview','dev','server'];
                    const play = document.querySelector('button:has(svg polygon), button:has(svg[viewBox*="play"])');
                    if (play && play.offsetParent !== null) {
                        play.click(); return { clicked: true, type: 'play-icon' };
                    }
                    for (const b of document.querySelectorAll('button, [role="button"]')) {
                        if (b.offsetParent === null) continue;
                        const t = (b.textContent||'').trim().toLowerCase();
                        const l = (b.getAttribute('aria-label')||'').toLowerCase();
                        const d = (b.getAttribute('data-testid')||'').toLowerCase();
                        if (t.includes('stop') || l.includes('stop')) continue;
                        for (const kw of kws) {
                            if (t === kw || t.startsWith(kw+' ') || l.includes(kw) || d.includes(kw)) {
                                const r = b.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) {
                                    b.click();
                                    return { clicked: true, text: t.slice(0,30) };
                                }
                            }
                        }
                    }
                    return { clicked: false };
                }
            """)
            if r and r.get('clicked'):
                log(f"✅ نقر JS: {r}")
                page.wait_for_timeout(5000)
                return "clicked"
        except:
            pass
        
        # اطبع الأزرار مرة واحدة
        if attempt == 0:
            try:
                info = page.evaluate("""
                    () => {
                        const a = [];
                        for (const b of document.querySelectorAll('button, [role="button"]')) {
                            if (b.offsetParent === null) continue;
                            const r = b.getBoundingClientRect();
                            if (r.width < 10 || r.height < 10) continue;
                            a.push({
                                text: (b.textContent||'').trim().slice(0,40),
                                label: (b.getAttribute('aria-label')||'').slice(0,40),
                                tid: (b.getAttribute('data-testid')||'').slice(0,40),
                                y: Math.round(r.y),
                            });
                        }
                        return a.slice(0, 25);
                    }
                """)
                log(f"📋 أزرار الصفحة ({len(info)}):")
                for b in info[:12]:
                    log(f"   y={b['y']} | text='{b['text']}' | label='{b['label']}' | tid='{b['tid']}'")
            except:
                pass
        
        if attempt < 7:
            page.wait_for_timeout(2000)
    
    return "not_found"


# ==================== الدورة الرئيسية ====================

def run_once():
    global last_update_time, last_status, last_project_opened, last_target_opened
    
    log("=" * 60)
    log("🔄 دورة جديدة")
    
    # تحميل الكوكيز
    cookies = load_cookies(REPLIT_COOKIE_FILE)
    if not cookies:
        log("❌ لا كوكيز! ضع ملف cookies.txt بجانب السكربت")
        last_status = "no_cookies"
        return False
    
    last_project_opened = False
    last_target_opened = False
    
    try:
        with sync_playwright() as p:
            browser, context = create_context(p, cookies)
            page = context.new_page()
            
            # ===== 1. فتح المشروع =====
            log(f"📂 فتح المشروع...")
            try:
                page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت المهلة")
                browser.close()
                last_status = "timeout"
                return False
            
            page.wait_for_timeout(8000)
            log(f"📍 URL: {page.url}")
            
            # تحقق من الجلسة
            if '/login' in page.url or '/signin' in page.url:
                log("❌ الكوكيز منتهية أو غير صالحة!")
                log("💡 صدّر كوكيز جديدة من متصفحك")
                try:
                    page.screenshot(path="debug_cookies_invalid.png")
                except:
                    pass
                browser.close()
                last_status = "cookies_invalid"
                return False
            
            log("✅ الجلسة صالحة!")
            last_project_opened = True
            
            try:
                page.screenshot(path="debug_project.png")
            except:
                pass
            
            # ===== 2. تشغيل المشروع =====
            result = click_run_or_workflow(page)
            log(f"📊 نتيجة البحث: {result}")
            
            if result == "clicked":
                page.wait_for_timeout(15000)
            elif result == "running":
                log("✅ المشروع يعمل")
            else:
                log("⚠️ لم يُعثر على زر التشغيل")
            
            # ===== 3. محاولة الحصول على رابط Webview من الصفحة =====
            webview_url = None
            try:
                for _ in range(5):
                    html = page.content()
                    m = re.search(r"https?://[a-f0-9\-]+\.replit\.dev(?::\d+)?", html)
                    if m:
                        webview_url = m.group(0)
                        break
                    page.wait_for_timeout(2000)
            except:
                pass
            
            if webview_url:
                log(f"🌐 Webview من الصفحة: {webview_url}")
            
            try:
                page.screenshot(path="debug_after_run.png")
            except:
                pass
            
            # ===== 4. فتح الرابط المستهدف =====
            log("=" * 60)
            log(f"🌐 فتح الرابط المستهدف...")
            
            try:
                page.goto(REPLIT_TARGET_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                
                title = page.title()
                body = ""
                try:
                    body = page.text_content("body") or ""
                except:
                    pass
                
                log(f"📄 العنوان: {title}")
                log(f"📄 محتوى (أول 200): {body[:200].strip()}")
                
                if body.strip():
                    last_target_opened = True
                    log("✅ الرابط فتح ويعرض محتوى!")
                else:
                    log("⚠️ الرابط فتح لكن فارغ")
                
                try:
                    page.screenshot(path="debug_target.png")
                except:
                    pass
            
            except PWTimeout:
                log("⚠️ انتهت مهلة الرابط المستهدف")
            except Exception as e:
                log(f"⚠️ خطأ الرابط: {e}")
            
            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        last_status = "error"
        return False
    
    # ===== حفظ الحالة =====
    last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if last_project_opened and last_target_opened:
        last_status = "success"
        log("✅ نجحت الدورة كاملة")
        with open("status.txt", "w") as f:
            f.write(f"status: success\nupdated: {last_update_time}\n")
            f.write(f"project: {REPLIT_PROJECT_URL}\n")
            f.write(f"target: {REPLIT_TARGET_URL}\n")
        return True
    elif last_project_opened:
        last_status = "project_ok_target_failed"
        return False
    else:
        last_status = "project_failed"
        return False


# ==================== Keep Alive ====================

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            color = '#00ff88' if last_status == 'success' else '#ffaa00'
            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
            <meta http-equiv="refresh" content="30"><title>Replit Keep Alive</title>
            <style>body{{font-family:Arial;text-align:center;padding:40px;
            background:#0a0a0a;color:#eee}}.box{{background:#1a1a2e;padding:20px;
            border-radius:10px;margin:15px auto;max-width:800px;border:1px solid #333}}
            .status{{color:{color};font-size:1.4em;font-weight:bold}}
            a{{color:#00ccff;word-break:break-all}}</style></head><body>
            <h1>🚀 Replit Keep Alive</h1>
            <div class="box">
                <div class="status">الحالة: {last_status}</div>
                <p>آخر تحديث: {last_update_time or '—'}</p>
                <p>الآن: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>المشروع: {'✅' if last_project_opened else '❌'}</p>
                <p>الهدف: {'✅' if last_target_opened else '❌'}</p>
            </div>
            <div class="box">
                <p><b>الهدف:</b></p>
                <a href="{REPLIT_TARGET_URL}" target="_blank">{REPLIT_TARGET_URL}</a>
            </div>
            </body></html>"""
            self.wfile.write(html.encode('utf-8'))
        elif p == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": last_status,
                "updated": last_update_time,
                "project_opened": last_project_opened,
                "target_opened": last_target_opened,
            }).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *args):
        pass


def run_keep_alive_server():
    try:
        server = HTTPServer(('0.0.0.0', KEEP_ALIVE_PORT), KeepAliveHandler)
        log(f"🔌 Keep Alive على {KEEP_ALIVE_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"⚠️ Keep Alive: {e}")


# ==================== Main ====================

def main():
    global running
    
    log("🔥 بدء السكربت - وضع الكوكيز الجاهزة")
    log(f"📁 كوكيز: {REPLIT_COOKIE_FILE}")
    
    # تحقق من وجود الكوكيز
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log(f"❌ الملف {REPLIT_COOKIE_FILE} غير موجود!")
        log(f"💡 ضع ملف الكوكيز بجانب السكربت بهذا الاسم بالضبط")
        sys.exit(1)
    
    cookies = load_cookies(REPLIT_COOKIE_FILE)
    if not cookies:
        log("❌ فشل تحميل الكوكيز!")
        sys.exit(1)
    
    log(f"✅ جاهز - {len(cookies)} كوكي")
    
    threading.Thread(target=run_keep_alive_server, daemon=True).start()
    
    while running:
        try:
            run_once()
            log(f"⏳ انتظار {REPLIT_REFRESH_INTERVAL}s...")
            for _ in range(REPLIT_REFRESH_INTERVAL):
                if not running:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            running = False
            break
        except Exception as e:
            log(f"❌ خطأ عام: {e}")
            time.sleep(10)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    main()
