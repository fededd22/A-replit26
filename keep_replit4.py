#!/usr/bin/env python3
"""
Replit - يدعم Workflows الجديدة بدلاً من زر Run
يبحث عن أي زر تشغيل: ▶ / Run / Start / Preview / Workflow
"""

import os
import sys
import json
import time
import re
import signal
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ==================== الإعدادات ====================
REPLIT_COOKIE_FILE = "cookies.txt"
REPLIT_PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REPLIT_LOGIN_URL = "https://replit.com/login"
REPLIT_REFRESH_INTERVAL = 30
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev(?::\d+)?"

REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"

KEEP_ALIVE_PORT = 8080
LOGIN_COOLDOWN = 90

running = True
last_webview_url = None
last_update_time = None
last_login_attempt = 0


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ==================== الكوكيز ====================

def load_cookies(cookie_file):
    if not os.path.exists(cookie_file):
        return []
    
    cookies = []
    try:
        with open(cookie_file) as f:
            content = f.read().strip()
        if content.startswith(('[', '{')):
            data = json.loads(content)
            if isinstance(data, dict) and 'cookies' in data:
                data = data['cookies']
            cookies = data
    except:
        pass
    
    if not cookies:
        import http.cookiejar
        try:
            jar = http.cookiejar.MozillaCookieJar(cookie_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            for c in jar:
                cookies.append({
                    'name': c.name, 'value': c.value,
                    'domain': c.domain, 'path': c.path or '/',
                    'secure': bool(c.secure),
                    'httpOnly': bool(c._rest.get('HttpOnly', False)) if hasattr(c, '_rest') else False,
                    'expires': c.expires,
                })
        except:
            pass
    
    filtered = []
    for c in cookies:
        domain = (c.get('domain') or '').lstrip('.').lower()
        if 'replit' not in domain:
            continue
        clean = {
            'name': c.get('name'), 'value': c.get('value'),
            'domain': domain, 'path': c.get('path', '/'),
        }
        if c.get('secure'): clean['secure'] = True
        if c.get('httpOnly'): clean['httpOnly'] = True
        if c.get('sameSite') in ('Strict', 'Lax', 'None'):
            clean['sameSite'] = c['sameSite']
        if isinstance(c.get('expires'), (int, float)) and c['expires'] > 0:
            clean['expires'] = int(c['expires'])
        if clean['name'] and clean['value']:
            filtered.append(clean)
    
    log(f"🍪 {len(filtered)} كوكي Replit (من {len(cookies)})")
    return filtered


def save_cookies(cookies, fname):
    try:
        with open(fname, 'w') as f:
            json.dump(cookies, f, indent=2)
        log(f"💾 حُفظت {len(cookies)} كوكي")
    except Exception as e:
        log(f"⚠️ خطأ الحفظ: {e}")


# ==================== سياق المتصفح ====================

def create_context(playwright, cookies=None, headless=True):
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            '--no-sandbox', '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--window-size=1920,1080',
        ]
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
    )
    
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [{name:'PDF Viewer'}, {name:'Chrome PDF Viewer'}]
        });
    """)
    
    if cookies:
        try:
            context.add_cookies(cookies)
            log(f"✅ أُضيفت {len(cookies)} كوكي")
        except Exception as e:
            log(f"⚠️ خطأ الكوكيز: {e}")
    
    return browser, context


def human_type(page, element, text):
    try:
        box = element.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2, steps=12)
            page.wait_for_timeout(250)
        element.click()
        page.wait_for_timeout(400)
        element.fill("")
        page.wait_for_timeout(200)
        for ch in text:
            element.type(ch)
            page.wait_for_timeout(40 + int(time.time()*1000) % 80)
    except Exception as e:
        log(f"⚠️ خطأ كتابة: {e}")


# ==================== تسجيل الدخول ====================

def login_replit() -> bool:
    global last_login_attempt
    now = time.time()
    if now - last_login_attempt < LOGIN_COOLDOWN:
        return False
    last_login_attempt = now
    
    log("=" * 60)
    log("🔑 تسجيل دخول Replit")
    
    try:
        with sync_playwright() as p:
            browser, context = create_context(p, headless=False)
            page = context.new_page()
            
            page.goto(REPLIT_LOGIN_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
            
            # بريد
            email_filled = False
            for sel in ['input[name="username"]', 'input[type="email"]',
                        'input#email', 'input[autocomplete="email"]']:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible(timeout=2000):
                        human_type(page, el, REPLIT_EMAIL)
                        log(f"✅ بريد → {sel}")
                        email_filled = True
                        break
                except:
                    continue
            
            if not email_filled:
                browser.close()
                return False
            
            page.wait_for_timeout(1500)
            
            # كلمة المرور
            pass_filled = False
            for sel in ['input[type="password"]', 'input[name="password"]']:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible(timeout=2000):
                        human_type(page, el, REPLIT_PASSWORD)
                        log(f"✅ كلمة المرور → {sel}")
                        pass_filled = True
                        break
                except:
                    continue
            
            if not pass_filled:
                browser.close()
                return False
            
            page.wait_for_timeout(1500)
            
            # زر الإرسال
            for sel in ['button[type="submit"]', 'button:has-text("Log in")',
                        'button:has-text("Sign in")']:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=2000):
                        btn.click()
                        log(f"✅ ضغط → {sel}")
                        break
                except:
                    continue
            
            page.wait_for_timeout(10000)
            
            # تحقق
            try:
                page.goto("https://replit.com/home", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)
            except:
                pass
            
            if "/login" in page.url or "/signin" in page.url:
                log("❌ فشل الدخول")
                browser.close()
                return False
            
            log("✅ نجح الدخول!")
            
            cookies_raw = context.cookies()
            cookies = []
            for c in cookies_raw:
                if 'replit' in c.get('domain', '').lower():
                    entry = {
                        'name': c['name'], 'value': c['value'],
                        'domain': c['domain'].lstrip('.'),
                        'path': c.get('path', '/'),
                        'secure': c.get('secure', False),
                        'httpOnly': c.get('httpOnly', False),
                        'sameSite': c.get('sameSite', 'Lax'),
                    }
                    if c.get('expires') and c['expires'] > 0:
                        entry['expires'] = int(c['expires'])
                    cookies.append(entry)
            
            browser.close()
            if cookies:
                save_cookies(cookies, REPLIT_COOKIE_FILE)
                return True
            return False
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return False


# ==================== زر التشغيل الجديد ====================

def click_run_or_workflow(page) -> str:
    """
    يدعم Replit الجديد: Workflows / Preview / Play button
    يُرجع: 'clicked' / 'running' / 'not_found'
    """
    log("🔍 البحث عن زر التشغيل (Run / Workflow / Play)...")
    
    # ===== 1. كشف إذا كان يعمل بالفعل =====
    running_indicators = [
        'button:has-text("Stop")',
        'button[aria-label*="Stop" i]',
        '[class*="console"]:has-text("running")',
        'text=/listening on|server started|running on port/i',
        'iframe[src*="replit.dev"]',
        'iframe[src*="replit.app"]',
        'iframe[title*="preview" i]',
        '[class*="preview-pane"]',
    ]
    
    for ind in running_indicators:
        try:
            el = page.locator(ind).first
            if el.count() > 0:
                try:
                    if el.is_visible(timeout=500):
                        log(f"✅ مؤشر التشغيل: {ind}")
                        return "running"
                except:
                    pass
        except:
            pass
    
    # ===== 2. selectors موسعة لأي زر تشغيل =====
    run_selectors = [
        # النص الصريح
        'button:has-text("Run")',
        '[role="button"]:has-text("Run")',
        'button:has-text("Start")',
        'button:has-text("Dev")',
        'button:has-text("Server")',
        'button:has-text("Launch")',
        'button:has-text("Preview")',
        # aria-label
        'button[aria-label="Run"]',
        'button[aria-label*="Run" i]',
        'button[aria-label*="Start" i]',
        'button[aria-label*="Play" i]',
        # data attributes
        '[data-testid="run-button"]',
        '[data-cy="run-button"]',
        '[data-testid*="run" i]',
        '[data-testid*="workflow" i]',
        # الأيقونات
        'button:has(svg[viewBox*="play"])',
        'button:has(svg polygon)',
    ]
    
    for attempt in range(12):
        # جرب selectors مباشرة
        for sel in run_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=1500):
                    el.click()
                    log(f"✅ تم النقر على: {sel}")
                    page.wait_for_timeout(5000)
                    return "clicked"
            except:
                continue
        
        # JavaScript - ابحث عن أي زر يشبه زر التشغيل
        try:
            result = page.evaluate("""
                () => {
                    // أولاً: زر فيه play icon
                    const svgPlay = document.querySelector('button:has(svg polygon), button:has(svg[viewBox*="play"])');
                    if (svgPlay && svgPlay.offsetParent !== null) {
                        const r = svgPlay.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            svgPlay.click();
                            return { clicked: true, type: 'svg-play' };
                        }
                    }
                    
                    // ثانياً: زر في الهيدر يحتوي على كلمات التشغيل
                    const keywords = ['run', 'start', 'play', 'preview', 'dev', 'server', 'launch'];
                    const buttons = document.querySelectorAll('button, [role="button"], a[role="button"]');
                    
                    for (const btn of buttons) {
                        if (btn.offsetParent === null) continue;
                        
                        const text = (btn.textContent || '').trim().toLowerCase();
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const testId = (btn.getAttribute('data-testid') || '').toLowerCase();
                        const cls = (btn.className || '').toString().toLowerCase();
                        
                        for (const kw of keywords) {
                            if (text === kw || text.includes(kw) || 
                                label.includes(kw) || testId.includes(kw)) {
                                // تحقق أنه ليس زر إيقاف
                                if (text.includes('stop') || label.includes('stop')) continue;
                                
                                const r = btn.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0 && r.top < 200) {
                                    btn.click();
                                    return { 
                                        clicked: true, 
                                        text: text.slice(0, 30),
                                        type: 'keyword',
                                        y: r.y
                                    };
                                }
                            }
                        }
                    }
                    
                    return { clicked: false };
                }
            """)
            
            if result and result.get('clicked'):
                log(f"✅ نقر عبر JS: {result}")
                page.wait_for_timeout(5000)
                return "clicked"
        except Exception as e:
            log(f"⚠️ خطأ JS: {e}")
        
        # اطبع ملخص الأزرار للتحليل
        if attempt == 0:
            try:
                buttons_info = page.evaluate("""
                    () => {
                        const result = [];
                        const buttons = document.querySelectorAll('button, [role="button"]');
                        for (const btn of buttons) {
                            if (btn.offsetParent === null) continue;
                            const r = btn.getBoundingClientRect();
                            if (r.width < 10 || r.height < 10) continue;
                            result.push({
                                text: (btn.textContent || '').trim().slice(0, 40),
                                label: (btn.getAttribute('aria-label') || '').slice(0, 40),
                                testid: (btn.getAttribute('data-testid') || '').slice(0, 40),
                                y: Math.round(r.y),
                                x: Math.round(r.x),
                            });
                        }
                        return result.slice(0, 30);
                    }
                """)
                log(f"📋 أزرار الصفحة ({len(buttons_info)}):")
                for b in buttons_info[:15]:
                    log(f"   y={b['y']} x={b['x']} | text='{b['text']}' | label='{b['label']}' | testid='{b['testid']}'")
            except Exception as e:
                log(f"⚠️ تعذر سرد الأزرار: {e}")
        
        if attempt < 11:
            page.wait_for_timeout(2000)
    
    return "not_found"


def get_webview_url(page):
    """استخراج رابط Webview من Preview"""
    log("🔍 البحث عن Webview URL...")
    
    # أنماط موسعة: replit.dev + replit.app + replit.co
    patterns = [
        r"https?://[a-f0-9\-]+\.replit\.dev(?::\d+)?",
        r"https?://[a-f0-9\-]+\.replit\.app(?::\d+)?",
        r"https?://[a-z0-9\-]+\.[a-z0-9\-]+\.replit\.dev(?::\d+)?",
    ]
    
    for _ in range(10):
        # من iframes
        try:
            for iframe in page.locator("iframe").all():
                src = iframe.get_attribute("src") or ""
                for pat in patterns:
                    m = re.search(pat, src)
                    if m:
                        return m.group(0)
        except:
            pass
        
        # من المحتوى
        try:
            html = page.content()
            for pat in patterns:
                matches = re.findall(pat, html)
                if matches:
                    return matches[0]
        except:
            pass
        
        # من عناصر منفصلة
        try:
            result = page.evaluate("""
                () => {
                    const patterns = [
                        /https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev(?::\\d+)?/,
                        /https?:\\/\\/[a-f0-9\\-]+\\.replit\\.app(?::\\d+)?/,
                    ];
                    
                    // in iframes
                    for (const f of document.querySelectorAll('iframe')) {
                        for (const p of patterns) {
                            const m = (f.src || '').match(p);
                            if (m) return m[0];
                        }
                    }
                    
                    // in text
                    const text = document.body.innerText || '';
                    for (const p of patterns) {
                        const m = text.match(p);
                        if (m) return m[0];
                    }
                    
                    // in links
                    for (const a of document.querySelectorAll('a[href]')) {
                        for (const p of patterns) {
                            const m = (a.href || '').match(p);
                            if (m) return m[0];
                        }
                    }
                    
                    return null;
                }
            """)
            if result:
                return result
        except:
            pass
        
        page.wait_for_timeout(2000)
    
    return None


# ==================== الدورة الرئيسية ====================

def open_project_once() -> bool:
    global last_webview_url, last_update_time
    
    log("=" * 60)
    log("🔄 دورة فتح المشروع")
    
    cookies = load_cookies(REPLIT_COOKIE_FILE)
    if not cookies:
        log("📂 لا كوكيز - تسجيل دخول...")
        if not login_replit():
            return False
        cookies = load_cookies(REPLIT_COOKIE_FILE)
        if not cookies:
            return False
    
    need_login = False
    webview_url = None
    
    try:
        with sync_playwright() as p:
            browser, context = create_context(p, cookies, headless=True)
            page = context.new_page()
            
            log(f"📂 فتح المشروع")
            try:
                page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت المهلة")
                browser.close()
                return False
            
            page.wait_for_timeout(10000)  # انتظار أطول للتحميل الكامل
            
            current_url = page.url
            log(f"📍 URL: {current_url}")
            
            try:
                page.screenshot(path="debug_project.png", full_page=False)
                log("📸 debug_project.png")
            except:
                pass
            
            if "/login" in current_url or "/signin" in current_url:
                log("❌ الكوكيز منتهية")
                need_login = True
            else:
                log("✅ فُتح المشروع")
                
                # انقر على زر التشغيل
                result = click_run_or_workflow(page)
                log(f"📊 نتيجة البحث: {result}")
                
                if result == "clicked":
                    page.wait_for_timeout(12000)  # وقت أطول للتشغيل
                elif result == "running":
                    log("✅ المشروع يعمل")
                else:
                    log("⚠️ لم يُعثر على زر تشغيل - جرب فتح Preview يدوياً")
                
                # استخرج الرابط
                webview_url = get_webview_url(page)
                
                if not webview_url:
                    # جرّب فتح علامة تبويب Preview
                    try:
                        preview_btn = page.locator('button:has-text("Preview"), [role="tab"]:has-text("Preview"), a:has-text("Preview")').first
                        if preview_btn.count() > 0:
                            preview_btn.click()
                            log("🖱️ فُتح Preview")
                            page.wait_for_timeout(8000)
                            webview_url = get_webview_url(page)
                    except:
                        pass
                
                if not webview_url:
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_timeout(8000)
                    webview_url = get_webview_url(page)
            
            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    if need_login:
        try:
            os.remove(REPLIT_COOKIE_FILE)
        except:
            pass
        if login_replit():
            return open_project_once()
        return False
    
    if webview_url:
        last_webview_url = webview_url
        last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log(f"🌐 Webview: {webview_url}")
        with open("webview_url.txt", "w") as f:
            f.write(f"{webview_url}\n{last_update_time}\n")
        return True
    else:
        log("⚠️ لا Webview")
        return False


# ==================== Keep Alive ====================

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
            <title>Keep Alive</title></head><body>
            <h1>🚀 Keep Alive</h1>
            <p>Webview: {last_webview_url or 'pending'}</p>
            <p>Updated: {last_update_time or '-'}</p>
            </body></html>"""
            self.wfile.write(html.encode('utf-8'))
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
        log(f"⚠️ خطأ: {e}")


# ==================== Main ====================

def main():
    global running
    
    log("🔥 بدء السكربت - دعم Workflows الجديدة")
    
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log("🔑 تسجيل دخول أولي...")
        login_replit()
    
    threading.Thread(target=run_keep_alive_server, daemon=True).start()
    
    while running:
        try:
            open_project_once()
            log(f"⏳ انتظار {REPLIT_REFRESH_INTERVAL}s...")
            for _ in range(REPLIT_REFRESH_INTERVAL):
                if not running:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            running = False
            break
        except Exception as e:
            log(f"❌ خطأ: {e}")
            time.sleep(10)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    main()
