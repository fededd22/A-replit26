#!/usr/bin/env python3
"""
سكربت Replit محسّن - يحاكي متصفحاً حقيقياً ويدخل للحساب بشكل طبيعي
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
running = True
last_webview_url = None
last_update_time = None


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ==================== تحميل/حفظ الكوكيز ====================

def load_cookies(cookie_file):
    """تحميل كوكيز بصيغة JSON أو Netscape مع تصفية كوكيز Replit فقط"""
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
            log(f"⚠️ فشل تحميل Netscape: {e}")
    
    # فلترة: كوكيز replit.com فقط (مهم جداً!)
    filtered = []
    for c in cookies:
        domain = (c.get('domain') or '').lstrip('.')
        if 'replit' in domain.lower():
            # تنظيف الحقول
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
    
    log(f"🍪 تمت تصفية {len(filtered)} كوكي Replit من أصل {len(cookies)}")
    return filtered


def save_cookies(cookies, cookie_file):
    """حفظ الكوكيز بصيغة JSON"""
    try:
        with open(cookie_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        log(f"💾 تم حفظ {len(cookies)} كوكي")
    except Exception as e:
        log(f"⚠️ خطأ حفظ الكوكيز: {e}")


# ==================== إعداد المتصفح الشبيه بالإنسان ====================

def create_stealth_context(playwright, cookies=None):
    """إنشاء سياق متصفح يحاكي مستخدماً حقيقياً"""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-web-security',
            '--window-size=1920,1080',
            '--start-maximized',
            # مفاتيح مهمة لتجاوز كشف الأتمتة
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
        permissions=['geolocation', 'notifications'],
        geolocation={"latitude": 24.7136, "longitude": 46.6753},
        color_scheme="light",
        device_scale_factor=1,
        has_touch=False,
        is_mobile=False,
        java_script_enabled=True,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    )
    
    # إخفاء كل علامات الأتمتة المعروفة
    context.add_init_script("""
        // إخفاء webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        
        // إضافة chrome runtime
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // إخفاء plugins فارغة
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'PDF Viewer', filename: 'internal-pdf-viewer'},
                {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer'},
                {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer'},
            ],
        });
        
        // اللغات
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en', 'ar']
        });
        
        // منصة
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // hardware
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        
        // إخفاء iframe detection
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
    
    # إضافة الكوكيز إذا وُجدت
    if cookies:
        try:
            context.add_cookies(cookies)
            log(f"✅ تمت إضافة {len(cookies)} كوكي إلى السياق")
        except Exception as e:
            log(f"⚠️ خطأ في إضافة الكوكيز: {e}")
    
    return browser, context


# ==================== تسجيل الدخول التفاعلي ====================

def login_interactive():
    """تسجيل دخول بطريقة تشبه الإنسان"""
    log("🔑 بدء تسجيل الدخول التفاعلي...")
    
    with sync_playwright() as p:
        browser, context = create_stealth_context(p)
        page = context.new_page()
        
        # فتح صفحة الدخول
        log(f"🌐 فتح {REPLIT_LOGIN_URL}")
        page.goto(REPLIT_LOGIN_URL, wait_until="networkidle", timeout=60000)
        
        # انتظار تحميل كامل
        page.wait_for_timeout(3000 + int(time.time() * 1000) % 2000)
        
        # لقطة تشخيصية
        try:
            page.screenshot(path="debug_login.png")
            log("📸 تم حفظ debug_login.png")
        except:
            pass
        
        # البحث عن حقل البريد بطريقة إنسانية
        log("📧 إدخال البريد الإلكتروني...")
        
        email_filled = False
        email_selectors = [
            'input[name="username"]',
            'input[type="email"]',
            'input#email',
            'input[autocomplete="email"]',
            'input[autocomplete="username"]',
        ]
        
        for sel in email_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=3000):
                    # حركة ماوس وهمية قبل الكتابة
                    box = el.bounding_box()
                    if box:
                        page.mouse.move(
                            box['x'] + box['width'] / 2,
                            box['y'] + box['height'] / 2,
                            steps=15
                        )
                        page.wait_for_timeout(300)
                    
                    el.click()
                    page.wait_for_timeout(500)
                    el.fill("")
                    page.wait_for_timeout(200)
                    
                    # كتابة حرف بحرف (بطيء) مع فواصل عشوائية
                    for char in REPLIT_EMAIL:
                        el.type(char)
                        page.wait_for_timeout(50 + int(time.time() * 1000) % 100)
                    
                    log(f"✅ تم إدخال البريد: {sel}")
                    email_filled = True
                    break
            except Exception as e:
                continue
        
        if not email_filled:
            log("❌ لم يتم العثور على حقل البريد")
            page.screenshot(path="debug_no_email_field.png")
            browser.close()
            return False
        
        page.wait_for_timeout(1000)
        
        # البحث عن حقل كلمة المرور
        log("🔒 إدخال كلمة المرور...")
        
        password_filled = False
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input#password',
            'input[autocomplete="current-password"]',
        ]
        
        for sel in password_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=3000):
                    box = el.bounding_box()
                    if box:
                        page.mouse.move(
                            box['x'] + box['width'] / 2,
                            box['y'] + box['height'] / 2,
                            steps=15
                        )
                        page.wait_for_timeout(300)
                    
                    el.click()
                    page.wait_for_timeout(500)
                    el.fill("")
                    page.wait_for_timeout(200)
                    
                    for char in REPLIT_PASSWORD:
                        el.type(char)
                        page.wait_for_timeout(50 + int(time.time() * 1000) % 100)
                    
                    log(f"✅ تم إدخال كلمة المرور: {sel}")
                    password_filled = True
                    break
            except:
                continue
        
        if not password_filled:
            log("❌ لم يتم العثور على حقل كلمة المرور")
            page.screenshot(path="debug_no_password_field.png")
            browser.close()
            return False
        
        page.wait_for_timeout(1000)
        
        # زر تسجيل الدخول
        log("🖱️ الضغط على زر تسجيل الدخول...")
        
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Log in")',
            'button:has-text("Sign in")',
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
                    log(f"✅ تم النقر على زر الدخول: {sel}")
                    submitted = True
                    break
            except:
                continue
        
        if not submitted:
            # محاولة الضغط على Enter
            page.keyboard.press("Enter")
            log("⌨️ تم الضغط على Enter")
        
        # انتظار النتيجة
        log("⏳ انتظار نتيجة تسجيل الدخول...")
        page.wait_for_timeout(8000)
        
        # التحقق من النتيجة
        current_url = page.url
        log(f"📍 URL الحالي: {current_url}")
        
        # التحقق من نجاح الدخول
        try:
            page.goto("https://replit.com/home", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            current_url = page.url
            log(f"📍 بعد فتح Home: {current_url}")
        except:
            pass
        
        if "login" in current_url.lower() or "signin" in current_url.lower():
            log("❌ فشل تسجيل الدخول - ما زلنا في صفحة الدخول")
            page.screenshot(path="debug_login_failed.png")
            browser.close()
            return False
        
        # نجح الدخول - احفظ الكوكيز
        log("✅ تم تسجيل الدخول بنجاح!")
        
        cookies_raw = context.cookies()
        # حفظ فقط كوكيز replit.com
        cookies = []
        for c in cookies_raw:
            if 'replit' in c.get('domain', '').lower():
                cookies.append({
                    'name': c['name'],
                    'value': c['value'],
                    'domain': c['domain'].lstrip('.'),
                    'path': c.get('path', '/'),
                    'secure': c.get('secure', False),
                    'httpOnly': c.get('httpOnly', False),
                    'sameSite': c.get('sameSite', 'Lax'),
                    **({'expires': int(c['expires'])} if c.get('expires') and c['expires'] > 0 else {}),
                })
        
        browser.close()
        
        if cookies:
            save_cookies(cookies, REPLIT_COOKIE_FILE)
            return True
        else:
            log("⚠️ لم يتم الحصول على كوكيز")
            return False


# ==================== فتح المشروع ====================

def find_run_button(page):
    """البحث عن زر Run بطرق متعددة"""
    log("🔍 البحث عن زر Run...")
    
    # selectors حسب الأولوية
    run_selectors = [
        # النص المباشر
        'button:has-text("Run")',
        '[role="button"]:has-text("Run")',
        # aria-label
        'button[aria-label="Run"]',
        'button[aria-label*="Run" i]',
        # data attributes
        '[data-cy="run-button"]',
        '[data-testid="run-button"]',
        # الأيقونة
        'button:has(svg[viewBox="0 0 24 24"])',
        # في الهيدر
        'header button:has-text("Run")',
        # المنسدلة
        'button[aria-haspopup="menu"]:has-text("Run")',
    ]
    
    for attempt in range(15):
        # 1. جرب selectors مباشرة
        for sel in run_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=2000):
                    text = (el.text_content() or "").strip()
                    label = el.get_attribute("aria-label") or ""
                    if "run" in text.lower() or "run" in label.lower():
                        log(f"✅ وجد زر Run عبر: {sel} (نص: '{text}')")
                        return el
            except:
                continue
        
        # 2. جرب JavaScript
        try:
            result = page.evaluate("""
                () => {
                    // ابحث في كل الأزرار
                    const buttons = document.querySelectorAll('button, [role="button"], a[role="button"]');
                    for (const btn of buttons) {
                        const text = (btn.textContent || '').trim().toLowerCase();
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const testId = (btn.getAttribute('data-testid') || '').toLowerCase();
                        
                        if ((text === 'run' || label.includes('run') || testId.includes('run')) 
                            && btn.offsetParent !== null) {
                            const rect = btn.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    x: rect.x + rect.width / 2,
                                    y: rect.y + rect.height / 2,
                                    text: text,
                                    tag: btn.tagName,
                                };
                            }
                        }
                    }
                    return null;
                }
            """)
            
            if result:
                log(f"✅ وجد زر Run عبر JS في ({result['x']}, {result['y']})")
                # انقر بإحداثيات الماوس (أكثر إنسانية)
                page.mouse.move(result['x'], result['y'], steps=10)
                page.wait_for_timeout(200)
                page.mouse.click(result['x'], result['y'])
                return True
        except:
            pass
        
        # 3. افحص حالة المشروع - ربما يعمل بالفعل
        try:
            # ابحث عن أي مؤشر على أن المشروع يعمل
            working_indicators = [
                'button:has-text("Stop")',
                '[class*="console"]',
                'iframe[src*="replit.dev"]',
                'text=/running|active|listening/i',
            ]
            for ind in working_indicators:
                el = page.locator(ind).first
                if el.count() > 0:
                    try:
                        if el.is_visible(timeout=500):
                            log(f"✅ المشروع يعمل بالفعل (مؤشر: {ind})")
                            return "already_running"
                    except:
                        pass
        except:
            pass
        
        if attempt < 14:
            log(f"⚠️ محاولة {attempt+1}/15...")
            page.wait_for_timeout(2000)
    
    return None


def get_webview_url(page):
    """استخراج رابط Webview"""
    log("🔍 البحث عن Webview URL...")
    
    for _ in range(10):
        # من iframes
        try:
            for iframe in page.locator("iframe").all():
                src = iframe.get_attribute("src") or ""
                m = re.search(WEBVIEW_PATTERN, src)
                if m:
                    return m.group(0)
        except:
            pass
        
        # من نص الصفحة
        try:
            html = page.content()
            matches = re.findall(WEBVIEW_PATTERN, html)
            if matches:
                return matches[0]
        except:
            pass
        
        page.wait_for_timeout(2000)
    
    return None


def open_project_once():
    """دورة واحدة لفتح المشروع"""
    global last_webview_url, last_update_time
    
    log("=" * 60)
    log("🔄 دورة فتح المشروع")
    
    cookies = load_cookies(REPLIT_COOKIE_FILE)
    
    if not cookies:
        log("📂 لا توجد كوكيز Replit - جاري تسجيل الدخول...")
        if not login_interactive():
            return False
        cookies = load_cookies(REPLIT_COOKIE_FILE)
        if not cookies:
            return False
    
    need_login = False
    webview_url = None
    
    try:
        with sync_playwright() as p:
            browser, context = create_stealth_context(p, cookies)
            page = context.new_page()
            
            log(f"📂 فتح المشروع: {REPLIT_PROJECT_URL}")
            try:
                page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت المهلة")
                browser.close()
                return False
            
            page.wait_for_timeout(6000)
            
            current_url = page.url
            log(f"📍 URL: {current_url}")
            
            # لقطة تشخيصية
            try:
                page.screenshot(path="debug_project.png")
            except:
                pass
            
            # التحقق من الدخول
            if "/login" in current_url or "/signin" in current_url:
                log("❌ الكوكيز منتهية")
                need_login = True
            else:
                log("✅ تم فتح المشروع")
                
                # ابحث عن زر Run
                result = find_run_button(page)
                
                if result is True:
                    log("✅ تم الضغط على Run")
                    page.wait_for_timeout(8000)
                elif result == "already_running":
                    log("✅ المشروع يعمل بالفعل")
                elif result is None:
                    log("⚠️ لم يُعثر على زر Run - ربما واجهة جديدة")
                
                # استخرج رابط Webview
                webview_url = get_webview_url(page)
                
                if not webview_url:
                    # جرب إعادة التحميل
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_timeout(5000)
                    webview_url = get_webview_url(page)
            
            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # إذا احتجنا تسجيل دخول
    if need_login:
        log("🔄 حذف الكوكيز القديمة وإعادة تسجيل الدخول...")
        try:
            os.remove(REPLIT_COOKIE_FILE)
        except:
            pass
        
        if login_interactive():
            return open_project_once()
        return False
    
    # حفظ النتيجة
    if webview_url:
        last_webview_url = webview_url
        last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log(f"🌐 Webview: {webview_url}")
        
        with open("webview_url.txt", "w") as f:
            f.write(f"{webview_url}\n{last_update_time}\n")
        
        return True
    else:
        log("⚠️ لم يتم العثور على رابط Webview")
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
            <h1>Keep Alive Active</h1>
            <p>Replit: {last_webview_url or 'pending'}</p>
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
    
    log("🔥 بدء السكربت")
    log(f"📁 كوكيز: {REPLIT_COOKIE_FILE}")
    
    # إذا لم توجد كوكيز، سجل دخول أولي
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log("🔑 لا توجد كوكيز - تسجيل دخول أولي...")
        login_interactive()
    
    threading.Thread(target=run_keep_alive_server, daemon=True).start()
    
    counter = 0
    while running:
        try:
            open_project_once()
            counter += 1
            
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
