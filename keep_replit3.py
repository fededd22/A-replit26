#!/usr/bin/env python3
"""
سكربت لتشغيل مشروع Replit مع Keep Alive - يحافظ على الجلسة نشطة مع إمكانية العمل المتزامن
مع خاصية تجديد الكوكيز تلقائياً
"""

import sys
import time
import http.cookiejar
import re
import os
import subprocess
import signal
import threading
import socket
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

# ==================== بيانات تسجيل الدخول ====================
REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"
# ============================================================

COOKIE_FILE = "cookies.txt"
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL_SECONDS = 10
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"
KEEP_ALIVE_PORT = 8080
PING_INTERVAL = 60
COOKIE_REFRESH_INTERVAL = 5  # تجديد الكوكيز كل ساعة


class KeepAliveHandler(BaseHTTPRequestHandler):
    """معالج طلبات HTTP لخدمة Keep Alive"""
    
    def do_GET(self):
        """معالجة طلبات GET"""
        parsed = urlparse(self.path)
        
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta http-equiv="refresh" content="30">
                <title>Keep Alive - Replit Session</title>
                <style>
                    body { font-family: Arial; text-align: center; padding: 50px; background: #0a0a0a; color: #00ff88; }
                    h1 { font-size: 3em; }
                    .status { font-size: 1.5em; margin: 20px 0; }
                    .time { color: #888; font-size: 0.8em; }
                    .success { color: #00ff88; }
                    .info { color: #666; font-size: 0.9em; margin: 10px 0; }
                </style>
            </head>
            <body>
                <h1>🚀 Keep Alive Active</h1>
                <div class="status success">✅ الجلسة نشطة ومستمرة</div>
                <div class="time">تم التحديث: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</div>
                <div class="info">🔑 آخر تجديد للكوكيز: """ + str(last_cookie_refresh or 'لم يتم') + """</div>
                <br>
                <div>⏳ تشغيل المشروع بشكل مستمر</div>
                <div style="margin-top: 30px; font-size: 0.9em; color: #666;">
                    <p>📱 يمكنك العمل في ترمينال آخر أثناء تشغيل هذا السكربت</p>
                    <p>🔄 يتم إعادة تشغيل المشروع كل """ + str(REFRESH_INTERVAL_SECONDS) + """ ثانية</p>
                    <p>🔄 يتم تجديد الكوكيز كل """ + str(COOKIE_REFRESH_INTERVAL // 60) + """ دقيقة</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode('utf-8'))
            
        elif parsed.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            status = f'{{"status": "running", "timestamp": "{datetime.now().isoformat()}", "interval": {REFRESH_INTERVAL_SECONDS}, "cookie_refresh": "{last_cookie_refresh or "never"}"}}'
            self.wfile.write(status.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass


# ==================== دوال تجديد الكوكيز ====================
last_cookie_refresh = None

def clean_cookie(cookie):
    """تنظيف الكوكي وإزالة الحقول غير الصالحة لـ Playwright"""
    allowed_fields = ['name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite']
    
    cleaned = {}
    for field in allowed_fields:
        if field in cookie:
            if field == 'expires':
                if isinstance(cookie[field], (int, float)):
                    cleaned[field] = cookie[field]
                elif isinstance(cookie[field], str):
                    try:
                        dt = datetime.fromisoformat(cookie[field].replace('Z', '+00:00'))
                        cleaned[field] = int(dt.timestamp())
                    except:
                        pass
            elif field == 'httpOnly':
                cleaned[field] = bool(cookie[field])
            elif field == 'secure':
                cleaned[field] = bool(cookie[field])
            elif field == 'sameSite':
                if cookie[field] in ['Strict', 'Lax', 'None']:
                    cleaned[field] = cookie[field]
            else:
                cleaned[field] = str(cookie[field])
    
    if 'name' not in cleaned or 'value' not in cleaned:
        return None
    
    if 'domain' in cleaned:
        cleaned['domain'] = cleaned['domain'].lstrip('.')
    
    return cleaned

def save_cookies(cookies):
    """حفظ الكوكيز بعد تنظيفها"""
    try:
        cleaned_cookies = []
        for cookie in cookies:
            cleaned = clean_cookie(cookie)
            if cleaned:
                cleaned_cookies.append(cleaned)
        
        with open(COOKIE_FILE, 'w') as f:
            json.dump(cleaned_cookies, f, indent=2)
        log(f"✅ تم حفظ {len(cleaned_cookies)} كوكي")
        return True
    except Exception as e:
        log(f"❌ خطأ في حفظ الكوكيز: {e}")
        return False

def login_to_replit():
    """تسجيل الدخول إلى Replit والحصول على كوكيز جديدة"""
    global last_cookie_refresh
    
    log("🔑 بدء تجديد الكوكيز...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--window-size=1280,720'
                ]
            )
            
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            
            log("🌐 فتح صفحة تسجيل الدخول...")
            page.goto("https://replit.com/login", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            log("📧 إدخال البريد الإلكتروني...")
            try:
                page.evaluate(f"""
                    const emailInput = document.querySelector('input[type="email"]');
                    if (emailInput) {{
                        emailInput.value = '{REPLIT_EMAIL}';
                        emailInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                """)
                page.wait_for_timeout(1000)
            except Exception as e:
                log(f"⚠️ خطأ في إدخال البريد: {e}")
            
            log("🔒 إدخال كلمة المرور...")
            try:
                page.evaluate(f"""
                    const passInput = document.querySelector('input[type="password"]');
                    if (passInput) {{
                        passInput.value = '{REPLIT_PASSWORD}';
                        passInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                """)
                page.wait_for_timeout(1000)
            except Exception as e:
                log(f"⚠️ خطأ في إدخال كلمة المرور: {e}")
            
            log("🖱️ الضغط على زر تسجيل الدخول...")
            try:
                login_selectors = [
                    "button:has-text('Log in')",
                    "button:has-text('Sign in')",
                    "button[type='submit']",
                    "button:has-text('Continue')"
                ]
                
                for selector in login_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.locator(selector).first.click()
                            log(f"✅ تم الضغط على الزر: {selector}")
                            page.wait_for_timeout(5000)
                            break
                    except:
                        continue
            except Exception as e:
                log(f"⚠️ خطأ في الضغط على زر تسجيل الدخول: {e}")
            
            page.wait_for_timeout(3000)
            current_url = page.url
            
            if "login" in current_url:
                log("❌ فشل تسجيل الدخول")
                browser.close()
                return False
            
            log("✅ تم تسجيل الدخول بنجاح!")
            
            cookies = context.cookies()
            cleaned_cookies = []
            for cookie in cookies:
                cleaned = clean_cookie(cookie)
                if cleaned:
                    cleaned_cookies.append(cleaned)
            
            browser.close()
            
            if cleaned_cookies:
                save_cookies(cleaned_cookies)
                last_cookie_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log(f"✅ تم تحديث الكوكيز ({len(cleaned_cookies)} كوكي)")
                return True
            else:
                log("❌ لم يتم الحصول على كوكيز صالحة")
                return False
    
    except Exception as e:
        log(f"❌ خطأ في تجديد الكوكيز: {e}")
        return False

def refresh_cookies_if_needed():
    """تجديد الكوكيز إذا كانت منتهية أو انتهى وقتها"""
    global last_cookie_refresh
    
    # التحقق من وجود ملف الكوكيز
    if not os.path.exists(COOKIE_FILE):
        log("📂 لا يوجد ملف كوكيز - جاري إنشاء جديد...")
        return login_to_replit()
    
    # التحقق من وقت آخر تجديد
    if last_cookie_refresh:
        try:
            last_time = datetime.strptime(last_cookie_refresh, "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.now() - last_time).total_seconds()
            if elapsed < COOKIE_REFRESH_INTERVAL:
                return True
        except:
            pass
    
    # تجديد الكوكيز
    log(f"⏰ حان وقت تجديد الكوكيز (آخر تحديث: {last_cookie_refresh})")
    return login_to_replit()

# ==================== دوال السكربت الأساسي ====================

def log(msg: str):
    """طباعة رسالة مع الطابع الزمني"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def netscape_cookie_to_playwright(cookie) -> dict:
    """تحويل الكوكيز إلى صيغة Playwright"""
    pw_cookie = {
        "name": cookie.get("name", ""),
        "value": cookie.get("value", ""),
        "domain": cookie.get("domain", ".replit.com"),
        "path": cookie.get("path", "/"),
        "secure": cookie.get("secure", False),
        "httpOnly": cookie.get("httpOnly", False),
    }
    if cookie.get("expires"):
        pw_cookie["expires"] = cookie["expires"]
    return pw_cookie


def load_cookies_for_playwright():
    """تحميل الكوكيز من الملف مع دعم تنسيق JSON الجديد"""
    if not os.path.exists(COOKIE_FILE):
        log(f"❌ ملف {COOKIE_FILE} غير موجود")
        return []
    
    try:
        # محاولة قراءة كـ JSON أولاً
        with open(COOKIE_FILE, 'r') as f:
            content = f.read().strip()
        
        # محاولة JSON
        try:
            cookies_data = json.loads(content)
            if isinstance(cookies_data, list):
                cookies = []
                for c in cookies_data:
                    cookies.append(netscape_cookie_to_playwright(c))
                log(f"✅ تم تحميل {len(cookies)} كوكي من JSON")
                return cookies
        except:
            pass
        
        # محاولة Netscape format (التنسيق القديم)
        jar = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            cookies = [netscape_cookie_to_playwright(c) for c in jar]
            log(f"✅ تم تحميل {len(cookies)} كوكي من Netscape")
            return cookies
        except:
            pass
        
        log("❌ لم يتم التعرف على تنسيق الكوكيز")
        return []
        
    except Exception as e:
        log(f"❌ خطأ في تحميل الكوكيز: {e}")
        return []


def press_run_button_with_retry(page, max_attempts=10):
    """محاولات للضغط على زر Run"""
    log("🔍 جاري البحث عن زر Run...")
    
    for attempt in range(max_attempts):
        page.wait_for_timeout(1500)
        
        selectors = [
            "button:has-text('Run')",
            "button[aria-label='Run']",
            "button[aria-label*='Run' i]",
            "[data-testid='run-button']",
            "[data-cy='run-button']",
            "button[data-testid='run-button']",
            ".run-button",
            "button[class*='run']",
            "button:has(svg[viewBox*='play'])",
            "button:has(span:has-text('Run'))",
            "header button:has-text('Run')",
        ]
        
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    text = btn.text_content() or ""
                    label = btn.get_attribute("aria-label") or ""
                    if "Run" in text or "run" in text.lower() or "Run" in label:
                        btn.click()
                        log(f"✅ تم الضغط على زر Run")
                        page.wait_for_timeout(5000)
                        return True
            except:
                continue
        
        # محاولة JavaScript
        try:
            result = page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button');
                    for (let btn of buttons) {
                        const text = (btn.textContent || '').toLowerCase();
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('run') || label.includes('run')) {
                            btn.click();
                            return 'clicked';
                        }
                    }
                    return 'not_found';
                }
            """)
            if result == 'clicked':
                log("✅ تم الضغط على زر Run عن طريق JavaScript")
                page.wait_for_timeout(5000)
                return True
        except:
            pass
        
        # التحقق من وجود زر Stop
        try:
            stop_btn = page.locator("button:has-text('Stop')").first
            if stop_btn.count() > 0 and stop_btn.is_visible(timeout=2000):
                log("✅ المشروع شغال بالفعل")
                return True
        except:
            pass
        
        if attempt < max_attempts - 1:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
    
    return False


def get_webview_url(page):
    """استخراج رابط Webview جديد"""
    log("🔍 البحث عن رابط Webview...")
    
    # البحث في iframes
    try:
        iframes = page.locator("iframe[src*='replit.dev']").all()
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            match = re.search(WEBVIEW_PATTERN, src)
            if match:
                url = match.group(0)
                log(f"✅ تم العثور على رابط Webview: {url}")
                return url
    except:
        pass
    
    # البحث في النص
    try:
        body = page.text_content("body") or ""
        matches = re.findall(WEBVIEW_PATTERN, body)
        if matches:
            url = matches[0]
            log(f"✅ تم العثور على رابط Webview: {url}")
            return url
    except:
        pass
    
    # البحث باستخدام JavaScript
    try:
        result = page.evaluate("""
            () => {
                const text = document.body.innerText || '';
                const match = text.match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                if (match) return match[0];
                
                const iframes = document.querySelectorAll('iframe');
                for (let iframe of iframes) {
                    const match = (iframe.src || '').match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                    if (match) return match[0];
                }
                return null;
            }
        """)
        if result:
            log(f"✅ تم العثور على رابط Webview: {result}")
            return result
    except:
        pass
    
    return None


def run_once():
    """تشغيل دورة واحدة مع تجديد الكوكيز إذا لزم الأمر"""
    log("🚀 بدء دورة جديدة")
    
    # تجديد الكوكيز إذا لزم الأمر
    if not refresh_cookies_if_needed():
        log("⚠️ فشل تجديد الكوكيز - استمرار بالكوكيز الحالية")
    
    cookies = load_cookies_for_playwright()
    if not cookies:
        log("❌ لا توجد كوكيز - محاولة تسجيل الدخول...")
        if login_to_replit():
            cookies = load_cookies_for_playwright()
        if not cookies:
            log("❌ فشل تحميل الكوكيز")
            return False

    webview_url = None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # إضافة الكوكيز
            valid_cookies = []
            for cookie in cookies:
                try:
                    context.add_cookies([cookie])
                    valid_cookies.append(cookie)
                except Exception as e:
                    continue
            
            if not valid_cookies:
                log("❌ لا توجد كوكيز صالحة - جاري تسجيل الدخول...")
                browser.close()
                if login_to_replit():
                    return run_once()
                return False
            
            page = context.new_page()

            log(f"📂 فتح المشروع")
            page.goto(PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            if "/login" in page.url:
                log("❌ الكوكيز منتهية - جاري تجديدها...")
                browser.close()
                if login_to_replit():
                    return run_once()
                return False

            log("✅ تم الدخول إلى المشروع")

            # تشغيل المشروع
            if press_run_button_with_retry(page, max_attempts=10):
                log("✅ تم تشغيل المشروع")
            else:
                log("⚠️ فشل تشغيل المشروع")

            # البحث عن رابط Webview
            for attempt in range(5):
                webview_url = get_webview_url(page)
                if webview_url:
                    break
                page.wait_for_timeout(2000)

            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return False
    
    # حفظ الرابط
    if webview_url:
        log(f"🌐 رابط Webview: {webview_url}")
        with open("webview_url.txt", "w") as f:
            f.write(f"{webview_url}\n")
            f.write(f"التحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n" + "="*60)
        print(f"🌐 {webview_url}")
        print("="*60 + "\n")
        return True
    else:
        log("⚠️ لم يتم العثور على رابط Webview")
        return False


def run_keep_alive_server():
    """تشغيل خادم Keep Alive في خيط منفصل"""
    try:
        server = HTTPServer(('0.0.0.0', KEEP_ALIVE_PORT), KeepAliveHandler)
        log(f"🔌 خادم Keep Alive يعمل على المنفذ {KEEP_ALIVE_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"⚠️ خطأ في خادم Keep Alive: {e}")


def main():
    """الحلقة الرئيسية مع Keep Alive وتجديد الكوكيز"""
    log("🔥 بدء التشغيل مع Keep Alive وتجديد الكوكيز التلقائي")
    log(f"⏱️ سيتم إعادة التشغيل كل {REFRESH_INTERVAL_SECONDS} ثانية")
    log(f"🔄 سيتم تجديد الكوكيز كل {COOKIE_REFRESH_INTERVAL // 60} دقيقة")
    log(f"🌐 خادم Keep Alive على المنفذ {KEEP_ALIVE_PORT}")
    log("📌 يمكنك فتح ترمينال آخر للعمل بشكل طبيعي")
    log(f"📧 البريد: {REPLIT_EMAIL}")
    
    # تشغيل خادم Keep Alive في خيط منفصل
    keep_alive_thread = threading.Thread(target=run_keep_alive_server, daemon=True)
    keep_alive_thread.start()
    
    # تجديد الكوكيز أول مرة
    log("🔄 جاري تجديد الكوكيز أول مرة...")
    login_to_replit()
    
    # بدء الحلقة الرئيسية
    while True:
        try:
            # تشغيل دورة واحدة
            run_once()
            
            # الانتظار
            log(f"⏳ الانتظار {REFRESH_INTERVAL_SECONDS} ثانية...")
            for i in range(REFRESH_INTERVAL_SECONDS, 0, -1):
                if i % 5 == 0 or i <= 3:
                    log(f"⏳ {i}s")
                time.sleep(1)
            
            log("🔄 بدء دورة جديدة...")
            print("-" * 50)
            
        except KeyboardInterrupt:
            log("⏹️ تم الإيقاف")
            break
        except Exception as e:
            log(f"❌ خطأ: {e}")
            time.sleep(3)


if __name__ == "__main__":
    # تجاهل إشارات المقاطعة للسماح بالعمل المتزامن
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    main()
