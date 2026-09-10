#!/usr/bin/env python3
"""
سكربت Replit - تسجيل دخول Email/Password فقط
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
REPLIT_USERNAME = "karimdeka85"
REPLIT_REPL_SLUG = "v2ray-vless-server-dashboard-5zip"
REPLIT_PROJECT_URL = f"https://replit.com/@{REPLIT_USERNAME}/{REPLIT_REPL_SLUG}"
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
    """تحميل كوكيز Replit فقط"""
    if not os.path.exists(cookie_file):
        return []
    
    cookies = []
    
    # JSON
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
    
    # Netscape
    if not cookies:
        import http.cookiejar
        try:
            jar = http.cookiejar.MozillaCookieJar(cookie_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            for c in jar:
                cookies.append({
                    'name': c.name,
                    'value': c.value,
                    'domain': c.domain,
                    'path': c.path or '/',
                    'secure': bool(c.secure),
                    'httpOnly': bool(c._rest.get('HttpOnly', False)) if hasattr(c, '_rest') else False,
                    'expires': c.expires,
                })
        except Exception as e:
            log(f"⚠️ خطأ Netscape: {e}")
    
    # فلترة: replit فقط
    filtered = []
    for c in cookies:
        domain = (c.get('domain') or '').lstrip('.').lower()
        if 'replit' not in domain:
            continue
        
        clean = {
            'name': c.get('name'),
            'value': c.get('value'),
            'domain': domain,
            'path': c.get('path', '/'),
        }
        if c.get('secure'): clean['secure'] = True
        if c.get('httpOnly'): clean['httpOnly'] = True
        if c.get('sameSite') in ('Strict', 'Lax', 'None'):
            clean['sameSite'] = c['sameSite']
        if isinstance(c.get('expires'), (int, float)) and c['expires'] > 0:
            clean['expires'] = int(c['expires'])
        
        if clean['name'] and clean['value']:
            filtered.append(clean)
    
    log(f"🍪 {len(filtered)} كوكي Replit (من أصل {len(cookies)})")
    return filtered


def save_cookies(cookies, cookie_file):
    try:
        with open(cookie_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        log(f"💾 حُفظت {len(cookies)} كوكي")
    except Exception as e:
        log(f"⚠️ خطأ الحفظ: {e}")


# ==================== سياق المتصفح ====================

def create_stealth_context(playwright, cookies=None, headless=True):
    """متصفح شبيه بالإنسان"""
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--window-size=1920,1080',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
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
        color_scheme="light",
        device_scale_factor=1,
    )
    
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined, configurable: true
        });
        window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name:'PDF Viewer', filename:'internal-pdf-viewer'},
                {name:'Chrome PDF Viewer', filename:'internal-pdf-viewer'},
                {name:'Chromium PDF Viewer', filename:'internal-pdf-viewer'},
            ]
        });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en','ar'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        const oq = window.navigator.permissions.query;
        window.navigator.permissions.query = (p) => (
            p.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : oq(p)
        );
    """)
    
    if cookies:
        try:
            context.add_cookies(cookies)
            log(f"✅ أُضيفت {len(cookies)} كوكي")
        except Exception as e:
            log(f"⚠️ خطأ الكوكيز: {e}")
    
    return browser, context


# ==================== كتابة إنسانية ====================

def human_type(page, element, text):
    """كتابة بطيئة مع حركة ماوس"""
    try:
        box = element.bounding_box()
        if box:
            page.mouse.move(
                box['x'] + box['width'] / 2,
                box['y'] + box['height'] / 2,
                steps=12
            )
            page.wait_for_timeout(250)
        
        element.click()
        page.wait_for_timeout(400)
        element.fill("")
        page.wait_for_timeout(200)
        
        for ch in text:
            element.type(ch)
            page.wait_for_timeout(40 + int(time.time() * 1000) % 80)
    except Exception as e:
        log(f"⚠️ خطأ كتابة: {e}")


# ==================== تسجيل الدخول ====================

def login_replit() -> bool:
    """تسجيل دخول Email/Password إلى Replit"""
    global last_login_attempt
    
    now = time.time()
    if now - last_login_attempt < LOGIN_COOLDOWN:
        wait = int(LOGIN_COOLDOWN - (now - last_login_attempt))
        log(f"⏸️ انتظار {wait}s قبل محاولة جديدة")
        return False
    last_login_attempt = now
    
    log("=" * 60)
    log("🔑 تسجيل دخول Replit (Email/Password)")
    
    try:
        with sync_playwright() as p:
            # headless=False لتحسين نجاح الدخول
            browser, context = create_stealth_context(p, headless=False)
            page = context.new_page()
            
            # ===== 1. فتح صفحة الدخول =====
            log(f"🌐 فتح {REPLIT_LOGIN_URL}")
            try:
                page.goto(REPLIT_LOGIN_URL, wait_until="networkidle", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت المهلة - متابعة على أي حال")
            
            page.wait_for_timeout(4000)
            log(f"📍 URL: {page.url}")
            
            try:
                page.screenshot(path="debug_login.png")
            except:
                pass
            
            # ===== 2. حقل البريد =====
            log("📧 إدخال البريد...")
            
            email_selectors = [
                'input[name="username"]',
                'input[type="email"]',
                'input#email',
                'input[autocomplete="email"]',
                'input[autocomplete="username"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="username" i]',
            ]
            
            email_filled = False
            for sel in email_selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible(timeout=3000):
                        human_type(page, el, REPLIT_EMAIL)
                        log(f"✅ بريد → {sel}")
                        email_filled = True
                        break
                except:
                    continue
            
            if not email_filled:
                log("❌ لم يُعثر على حقل البريد")
                try:
                    page.screenshot(path="debug_no_email.png")
                except:
                    pass
                browser.close()
                return False
            
            page.wait_for_timeout(1500)
            
            # ===== 3. حقل كلمة المرور =====
            log("🔒 إدخال كلمة المرور...")
            
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input#password',
                'input[autocomplete="current-password"]',
            ]
            
            pass_filled = False
            for sel in password_selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible(timeout=3000):
                        human_type(page, el, REPLIT_PASSWORD)
                        log(f"✅ كلمة المرور → {sel}")
                        pass_filled = True
                        break
                except:
                    continue
            
            if not pass_filled:
                log("❌ لم يُعثر على حقل كلمة المرور")
                try:
                    page.screenshot(path="debug_no_password.png")
                except:
                    pass
                browser.close()
                return False
            
            page.wait_for_timeout(1500)
            
            # ===== 4. زر الإرسال =====
            log("🖱️ الضغط على زر الدخول...")
            
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                'button:has-text("Login")',
                'button:has-text("Continue")',
                'input[type="submit"]',
            ]
            
            submitted = False
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=2000):
                        box = btn.bounding_box()
                        if box:
                            page.mouse.move(
                                box['x'] + box['width'] / 2,
                                box['y'] + box['height'] / 2,
                                steps=10
                            )
                            page.wait_for_timeout(200)
                        btn.click()
                        log(f"✅ ضغط → {sel}")
                        submitted = True
                        break
                except:
                    continue
            
            if not submitted:
                page.keyboard.press("Enter")
                log("⌨️ Enter")
            
            # ===== 5. انتظار النتيجة =====
            log("⏳ انتظار النتيجة...")
            page.wait_for_timeout(10000)
            
            current_url = page.url
            log(f"📍 URL بعد الدخول: {current_url}")
            
            try:
                page.screenshot(path="debug_after_submit.png")
            except:
                pass
            
            # ===== 6. تحقق =====
            if "/login" in current_url or "/signin" in current_url:
                # جرّب فتح home للتحقق النهائي
                try:
                    page.goto("https://replit.com/home", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)
                    current_url = page.url
                    log(f"📍 بعد home: {current_url}")
                except:
                    pass
            
            if "/login" in current_url or "/signin" in current_url:
                log("❌ فشل الدخول - تحقق من بيانات الدخول")
                try:
                    page.screenshot(path="debug_login_failed.png")
                except:
                    pass
                browser.close()
                return False
            
            # ===== 7. نجح - احفظ الكوكيز =====
            log("✅ نجح تسجيل الدخول!")
            
            cookies_raw = context.cookies()
            cookies = []
            for c in cookies_raw:
                if 'replit' in c.get('domain', '').lower():
                    entry = {
                        'name': c['name'],
                        'value': c['value'],
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
            else:
                log("⚠️ لا كوكيز")
                return False
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== فتح المشروع ====================

def find_run_button(page):
    """البحث عن زر Run"""
    log("🔍 البحث عن زر Run...")
    
    selectors = [
        'button:has-text("Run")',
        '[role="button"]:has-text("Run")',
        'button[aria-label="Run"]',
        'button[aria-label*="Run" i]',
        '[data-cy="run-button"]',
        '[data-testid="run-button"]',
        'header button:has-text("Run")',
    ]
    
    for attempt in range(10):
        # تحقق إذا كان يعمل
        try:
            stop = page.locator('button:has-text("Stop")').first
            if stop.count() > 0 and stop.is_visible(timeout=800):
                log("✅ المشروع يعمل بالفعل")
                return "already_running"
        except:
            pass
        
        # جرب selectors
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=1500):
                    text = (el.text_content() or "").strip().lower()
                    label = (el.get_attribute("aria-label") or "").lower()
                    if "run" in text or "run" in label:
                        log(f"✅ زر Run → {sel}")
                        el.click()
                        return True
            except:
                continue
        
        # JavaScript
        try:
            result = page.evaluate("""
                () => {
                    const els = document.querySelectorAll('button, [role="button"], a[role="button"]');
                    for (const el of els) {
                        const t = (el.textContent || '').trim().toLowerCase();
                        const l = (el.getAttribute('aria-label') || '').toLowerCase();
                        const d = (el.getAttribute('data-testid') || '').toLowerCase();
                        if ((t === 'run' || l.includes('run') || d.includes('run')) 
                            && el.offsetParent !== null) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                el.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """)
            if result:
                log("✅ زر Run عبر JS")
                return True
        except:
            pass
        
        if attempt < 9:
            page.wait_for_timeout(2000)
    
    return None


def get_webview_url(page):
    """استخراج رابط Webview"""
    log("🔍 البحث عن Webview...")
    
    for _ in range(8):
        try:
            for iframe in page.locator("iframe").all():
                src = iframe.get_attribute("src") or ""
                m = re.search(WEBVIEW_PATTERN, src)
                if m:
                    return m.group(0)
        except:
            pass
        
        try:
            html = page.content()
            matches = re.findall(WEBVIEW_PATTERN, html)
            if matches:
                return matches[0]
        except:
            pass
        
        page.wait_for_timeout(2000)
    
    return None


def open_project_once() -> bool:
    """دورة فتح المشروع"""
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
            browser, context = create_stealth_context(p, cookies, headless=True)
            page = context.new_page()
            
            log(f"📂 فتح المشروع")
            try:
                page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت المهلة")
                browser.close()
                return False
            
            page.wait_for_timeout(7000)
            
            current_url = page.url
            log(f"📍 URL: {current_url}")
            
            try:
                page.screenshot(path="debug_project.png")
            except:
                pass
            
            if "/login" in current_url or "/signin" in current_url:
                log("❌ الكوكيز منتهية")
                need_login = True
            else:
                log("✅ فُتح المشروع")
                
                result = find_run_button(page)
                if result is True:
                    log("✅ تم الضغط على Run")
                    page.wait_for_timeout(10000)
                elif result == "already_running":
                    log("✅ المشروع يعمل")
                else:
                    log("⚠️ لم يُعثر على زر Run")
                
                webview_url = get_webview_url(page)
                
                if not webview_url:
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_timeout(5000)
                    webview_url = get_webview_url(page)
            
            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return False
    
    if need_login:
        log("🔄 حذف الكوكيز وإعادة الدخول...")
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
            <p>Now: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
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
        log(f"⚠️ خطأ Keep Alive: {e}")


# ==================== Main ====================

def main():
    global running
    
    log("🔥 بدء السكربت - Replit Email/Password فقط")
    log(f"📁 كوكيز: {REPLIT_COOKIE_FILE}")
    
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log("🔑 لا كوكيز - تسجيل دخول أولي...")
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
