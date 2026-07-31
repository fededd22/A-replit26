#!/usr/bin/env python3
"""
سكربت Keep Alive مع Playwright - يعمل في Cloud Shell
مع تصحيح مشكلة الكوكيز
"""

import os
import sys
import time
import json
import re
import threading
import signal
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

# ==================== بيانات تسجيل الدخول ====================
REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"
# ============================================================

# إعدادات
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL = 300  # 5 دقائق للاختبار
KEEP_ALIVE_PORT = int(os.environ.get('PORT', 8080))
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"
COOKIE_FILE = "cookies.txt"

# متغيرات عامة
last_webview_url = None
last_update_time = None
last_login_time = None
running = True


class KeepAliveHandler(BaseHTTPRequestHandler):
    """خادم HTTP لعرض الحالة"""
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            status_color = "#00ff88" if last_webview_url else "#ff8800"
            status_text = "✅ نشط" if last_webview_url else "⏳ في انتظار التشغيل"
            
            html = f"""
            <!DOCTYPE html>
            <html lang="ar">
            <head>
                <meta charset="UTF-8">
                <meta http-equiv="refresh" content="30">
                <title>🚀 Replit Keep Alive</title>
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{ 
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        text-align: center; 
                        padding: 20px; 
                        background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
                        color: #00ff88;
                        min-height: 100vh;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                    }}
                    .container {{ 
                        background: rgba(0,0,0,0.85); 
                        padding: 40px; 
                        border-radius: 30px; 
                        max-width: 700px; 
                        width: 90%;
                        border: 2px solid #00ff88;
                        box-shadow: 0 0 60px rgba(0,255,136,0.15);
                    }}
                    h1 {{ 
                        font-size: 2.8em; 
                        margin-bottom: 10px;
                        background: linear-gradient(45deg, #00ff88, #00ccff);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                    }}
                    .status {{ 
                        font-size: 2em; 
                        color: {status_color}; 
                        margin: 20px 0;
                    }}
                    .url {{ 
                        color: #00ccff; 
                        word-break: break-all;
                        background: rgba(0,0,0,0.5);
                        padding: 20px;
                        border-radius: 15px;
                        margin: 20px 0;
                        font-size: 1em;
                        border: 1px solid rgba(0,204,255,0.2);
                    }}
                    .info {{ 
                        color: #888; 
                        font-size: 0.9em; 
                        margin: 10px 0;
                    }}
                    .badge {{
                        display: inline-block;
                        padding: 5px 15px;
                        background: rgba(0,255,136,0.1);
                        border-radius: 20px;
                        margin: 5px;
                        font-size: 0.8em;
                        border: 1px solid rgba(0,255,136,0.2);
                    }}
                    .footer {{
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 1px solid rgba(255,255,255,0.05);
                        color: #444;
                        font-size: 0.8em;
                    }}
                    a {{ color: #00ccff; text-decoration: none; }}
                    .time {{ color: #00ff88; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚀 Keep Alive</h1>
                    <div class="status">{status_text}</div>
                    <div class="url">🌐 {last_webview_url or '⏳ جاري البحث عن الرابط...'}</div>
                    <div class="info">⏱️ آخر تحديث: <span class="time">{last_update_time or 'لم يتم التحديث'}</span></div>
                    <div class="info">🔑 آخر تسجيل دخول: <span class="time">{last_login_time or 'لم يتم تسجيل الدخول'}</span></div>
                    <div style="margin-top: 20px;">
                        <span class="badge">🔄 كل {REFRESH_INTERVAL} ثانية</span>
                        <span class="badge">☁️ Cloud Shell</span>
                        <span class="badge">🎭 Playwright</span>
                        <span class="badge">🔑 Auto Login</span>
                    </div>
                    <div class="footer">
                        <p>📊 <a href="/status">حالة JSON</a></p>
                    </div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
        
        elif parsed.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            data = {
                "status": "running" if last_webview_url else "waiting",
                "webview_url": last_webview_url,
                "last_update": last_update_time,
                "last_login": last_login_time,
                "interval": REFRESH_INTERVAL,
                "platform": "Cloud Shell",
                "engine": "Playwright"
            }
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        pass


def log(msg):
    """طباعة رسالة مع الوقت"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def clean_cookie(cookie):
    """تنظيف الكوكي وإزالة الحقول غير الصالحة لـ Playwright"""
    # الحقول المسموح بها في Playwright
    allowed_fields = ['name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite']
    
    cleaned = {}
    for field in allowed_fields:
        if field in cookie:
            # تحويل القيم إلى الأنواع الصحيحة
            if field == 'expires':
                # تحويل التاريخ إلى رقم (timestamp)
                if isinstance(cookie[field], (int, float)):
                    cleaned[field] = cookie[field]
                elif isinstance(cookie[field], str):
                    try:
                        # محاولة تحويل النص إلى timestamp
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
    
    # التأكد من وجود الحقول الأساسية
    if 'name' not in cleaned or 'value' not in cleaned:
        return None
    
    # تنظيف القيم
    if 'domain' in cleaned:
        cleaned['domain'] = cleaned['domain'].lstrip('.')
    
    return cleaned


def save_cookies(cookies):
    """حفظ الكوكيز بعد تنظيفها"""
    try:
        # تنظيف الكوكيز قبل الحفظ
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
    """تسجيل الدخول إلى Replit باستخدام Playwright"""
    global last_login_time
    
    log("🔑 بدء تسجيل الدخول إلى Replit...")
    
    try:
        with sync_playwright() as p:
            # إعداد المتصفح
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
            
            # فتح صفحة تسجيل الدخول
            log("🌐 فتح صفحة تسجيل الدخول...")
            page.goto("https://replit.com/login", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # إدخال البريد الإلكتروني
            log("📧 إدخال البريد الإلكتروني...")
            try:
                # استخدام JavaScript لإدخال البريد
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
            
            # إدخال كلمة المرور
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
            
            # الضغط على زر تسجيل الدخول
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
            
            # التحقق من نجاح تسجيل الدخول
            page.wait_for_timeout(3000)
            current_url = page.url
            
            if "login" in current_url:
                log("❌ فشل تسجيل الدخول - تحقق من البريد وكلمة المرور")
                browser.close()
                return None
            
            log("✅ تم تسجيل الدخول بنجاح!")
            
            # الحصول على الكوكيز
            cookies = context.cookies()
            
            # تنظيف الكوكيز
            cleaned_cookies = []
            for cookie in cookies:
                cleaned = clean_cookie(cookie)
                if cleaned:
                    cleaned_cookies.append(cleaned)
            
            browser.close()
            
            last_login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log(f"✅ تم الحصول على {len(cleaned_cookies)} كوكي")
            return cleaned_cookies
    
    except Exception as e:
        log(f"❌ خطأ في تسجيل الدخول: {e}")
        return None


def get_webview_url():
    """الحصول على رابط Webview باستخدام Playwright"""
    global last_webview_url, last_update_time
    
    # تحميل الكوكيز من الملف
    cookies = None
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r') as f:
                cookies = json.loads(f.read())
                log(f"📂 تم تحميل {len(cookies)} كوكي من الملف")
        except Exception as e:
            log(f"⚠️ خطأ في قراءة الملف: {e}")
    
    # إذا لم توجد كوكيز، قم بتسجيل الدخول
    if not cookies:
        log("🔑 لا توجد كوكيز - جاري تسجيل الدخول...")
        cookies = login_to_replit()
        if cookies:
            save_cookies(cookies)
        else:
            log("❌ فشل تسجيل الدخول")
            return None
    
    try:
        with sync_playwright() as p:
            # إعداد المتصفح
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
            
            # إضافة الكوكيز واحدة تلو الأخرى مع تجاهل الكوكيز الفاسدة
            valid_cookies = []
            for cookie in cookies:
                try:
                    context.add_cookies([cookie])
                    valid_cookies.append(cookie)
                except Exception as e:
                    log(f"⚠️ تجاهل كوكي غير صالح: {cookie.get('name', 'unknown')}")
                    continue
            
            if not valid_cookies:
                log("❌ لا توجد كوكيز صالحة - جاري تسجيل الدخول مجدداً...")
                browser.close()
                new_cookies = login_to_replit()
                if new_cookies:
                    save_cookies(new_cookies)
                    return get_webview_url()
                return None
            
            log(f"✅ تم إضافة {len(valid_cookies)} كوكي صالح")
            
            page = context.new_page()
            
            log(f"📂 فتح المشروع...")
            page.goto(PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            
            # التحقق من الدخول
            current_url = page.url
            if "login" in current_url.lower():
                log("⚠️ الكوكيز منتهية - جاري تسجيل الدخول مجدداً...")
                browser.close()
                
                # تسجيل الدخول مجدداً
                new_cookies = login_to_replit()
                if new_cookies:
                    save_cookies(new_cookies)
                    return get_webview_url()
                return None
            
            log("✅ تم الدخول إلى المشروع")
            
            # البحث عن زر Run والضغط عليه
            log("🔍 البحث عن زر Run...")
            try:
                run_selectors = [
                    "button:has-text('Run')",
                    "button[aria-label='Run']",
                    "button[data-testid='run-button']",
                    "button[class*='run']"
                ]
                
                for selector in run_selectors:
                    if page.locator(selector).count() > 0:
                        page.locator(selector).first.click()
                        log("✅ تم الضغط على زر Run")
                        page.wait_for_timeout(5000)
                        break
            except Exception as e:
                log(f"⚠️ زر Run غير موجود أو المشروع يعمل: {e}")
            
            # البحث عن رابط Webview
            log("🔍 البحث عن رابط Webview...")
            webview_url = None
            
            # البحث في iframes
            try:
                iframes = page.locator("iframe[src*='replit.dev']").all()
                for iframe in iframes:
                    src = iframe.get_attribute("src") or ""
                    match = re.search(WEBVIEW_PATTERN, src)
                    if match:
                        webview_url = match.group(0)
                        break
            except:
                pass
            
            # البحث في محتوى الصفحة
            if not webview_url:
                try:
                    content = page.content()
                    matches = re.findall(WEBVIEW_PATTERN, content)
                    if matches:
                        webview_url = matches[0]
                except:
                    pass
            
            # البحث باستخدام JavaScript
            if not webview_url:
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
                        webview_url = result
                except:
                    pass
            
            browser.close()
            
            if webview_url:
                last_webview_url = webview_url
                last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log(f"✅ تم العثور على الرابط: {webview_url}")
                
                # حفظ الرابط في ملف
                with open("webview_url.txt", "w") as f:
                    f.write(f"{webview_url}\n")
                    f.write(f"آخر تحديث: {last_update_time}\n")
                
                print("\n" + "="*60)
                print(f"🌐 {webview_url}")
                print("="*60 + "\n")
                
                return webview_url
            else:
                log("⚠️ لم يتم العثور على رابط Webview")
                return None
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return None


def run_server():
    """تشغيل خادم HTTP"""
    try:
        server = HTTPServer(('0.0.0.0', KEEP_ALIVE_PORT), KeepAliveHandler)
        log(f"🌐 خادم HTTP يعمل على http://localhost:{KEEP_ALIVE_PORT}")
        log(f"📱 افتح في المتصفح: http://localhost:{KEEP_ALIVE_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"❌ خطأ في الخادم: {e}")


def main():
    global running
    
    log("🔥 بدء Keep Alive مع Playwright (Cloud Shell)")
    log(f"📧 البريد: {REPLIT_EMAIL}")
    log(f"⏱️ التحديث كل {REFRESH_INTERVAL} ثانية")
    log(f"🌐 المنفذ: {KEEP_ALIVE_PORT}")
    
    # تشغيل الخادم في خيط منفصل
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2)
    
    # الحلقة الرئيسية
    while running:
        try:
            get_webview_url()
            
            log(f"⏳ الانتظار {REFRESH_INTERVAL} ثانية...")
            time.sleep(REFRESH_INTERVAL)
            
            log("🔄 بدء دورة جديدة...")
            print("-" * 50)
        
        except KeyboardInterrupt:
            log("⏹️ تم الإيقاف")
            running = False
            break
        except Exception as e:
            log(f"❌ خطأ: {e}")
            time.sleep(30)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    main()
