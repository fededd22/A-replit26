#!/usr/bin/env python3
"""
سكربت Keep Alive مع تسجيل دخول تلقائي إلى Replit
"""

import os
import sys
import time
import json
import re
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("❌ Selenium غير مثبت. قم بتشغيل: pip install selenium")

# ==================== بيانات تسجيل الدخول ====================
REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"
# ============================================================

# إعدادات
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL = 10  # 30 دقيقة
KEEP_ALIVE_PORT = int(os.environ.get('PORT', 8080))
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"
COOKIE_FILE = "cookies.txt"

# مسارات Termux
CHROMEDRIVER_PATH = "/data/data/com.termux/files/usr/bin/chromedriver"
CHROMIUM_PATH = "/data/data/com.termux/files/usr/bin/chromium"

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
            
            html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta http-equiv="refresh" content="30">
                <title>Replit Keep Alive</title>
                <style>
                    body {{ 
                        font-family: 'Segoe UI', Arial, sans-serif;
                        text-align: center; 
                        padding: 20px; 
                        background: linear-gradient(135deg, #0a0a0a, #1a1a2e);
                        color: #00ff88;
                        margin: 0;
                        min-height: 100vh;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                    }}
                    .container {{ 
                        background: rgba(0,0,0,0.8); 
                        padding: 30px; 
                        border-radius: 20px; 
                        max-width: 650px; 
                        width: 90%;
                        border: 1px solid #00ff88;
                        box-shadow: 0 0 40px rgba(0,255,136,0.1);
                    }}
                    h1 {{ 
                        font-size: 2.5em; 
                        margin: 0 0 10px 0;
                        background: linear-gradient(45deg, #00ff88, #00ccff);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                    }}
                    .status {{ font-size: 1.8em; color: {status_color}; margin: 15px 0; }}
                    .url {{ 
                        color: #00ccff; 
                        word-break: break-all;
                        background: rgba(0,0,0,0.5);
                        padding: 15px;
                        border-radius: 10px;
                        margin: 15px 0;
                        font-size: 0.9em;
                        border: 1px solid rgba(0,204,255,0.2);
                    }}
                    .info {{ color: #888; font-size: 0.85em; margin: 10px 0; }}
                    .badge {{
                        display: inline-block;
                        padding: 4px 12px;
                        background: rgba(0,255,136,0.1);
                        border-radius: 20px;
                        margin: 4px;
                        font-size: 0.75em;
                        border: 1px solid rgba(0,255,136,0.2);
                    }}
                    .footer {{ margin-top: 20px; font-size: 0.75em; color: #666; }}
                    a {{ color: #00ccff; text-decoration: none; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚀 Keep Alive</h1>
                    <div class="status">{status_text}</div>
                    <div class="url">🌐 {last_webview_url or '⏳ جاري الانتظار...'}</div>
                    <div class="info">⏱️ آخر تحديث: {last_update_time or 'لم يتم التحديث'}</div>
                    <div class="info">🔑 آخر تسجيل دخول: {last_login_time or 'لم يتم تسجيل الدخول'}</div>
                    <div style="margin-top: 15px;">
                        <span class="badge">🔄 كل {REFRESH_INTERVAL} ثانية</span>
                        <span class="badge">📱 Termux</span>
                        <span class="badge">🔑 Auto Login</span>
                    </div>
                    <div class="footer">
                        <a href="/status">📊 JSON Status</a>
                    </div>
                </div>
            </body>
            </html>
            '''
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
                "platform": "Termux"
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
        
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        pass


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def save_cookies(cookies):
    """حفظ الكوكيز في ملف"""
    try:
        with open(COOKIE_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        log(f"✅ تم حفظ {len(cookies)} كوكي")
        return True
    except Exception as e:
        log(f"❌ خطأ في حفظ الكوكيز: {e}")
        return False


def login_to_replit():
    """تسجيل الدخول إلى Replit والحصول على الكوكيز"""
    global last_login_time
    
    log("🔑 بدء تسجيل الدخول إلى Replit...")
    
    if not SELENIUM_AVAILABLE:
        log("❌ Selenium غير متوفر")
        return None
    
    if not os.path.exists(CHROMEDRIVER_PATH):
        log(f"❌ ChromeDriver غير موجود في: {CHROMEDRIVER_PATH}")
        return None
    
    driver = None
    try:
        # إعداد المتصفح
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1280,720')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        if os.path.exists(CHROMIUM_PATH):
            options.binary_location = CHROMIUM_PATH
        
        service = Service(executable_path=CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(45)
        
        # فتح صفحة تسجيل الدخول
        log("🌐 فتح صفحة تسجيل الدخول...")
        driver.get("https://replit.com/login")
        time.sleep(3)
        
        # إدخال البريد الإلكتروني
        log("📧 إدخال البريد الإلكتروني...")
        try:
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[placeholder*='Email']"))
            )
            email_input.clear()
            email_input.send_keys(REPLIT_EMAIL)
            time.sleep(1)
        except Exception as e:
            log(f"⚠️ خطأ في إدخال البريد: {e}")
        
        # إدخال كلمة المرور
        log("🔒 إدخال كلمة المرور...")
        try:
            password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password'], input[name='password']")
            password_input.clear()
            password_input.send_keys(REPLIT_PASSWORD)
            time.sleep(1)
        except Exception as e:
            log(f"⚠️ خطأ في إدخال كلمة المرور: {e}")
        
        # الضغط على زر تسجيل الدخول
        log("🖱️ الضغط على زر تسجيل الدخول...")
        try:
            login_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Log in') or contains(text(), 'Sign in')]")
            login_button.click()
            time.sleep(5)
        except Exception as e:
            log(f"⚠️ خطأ في الضغط على زر تسجيل الدخول: {e}")
        
        # انتظار تحميل الصفحة
        time.sleep(5)
        
        # التحقق من نجاح تسجيل الدخول
        current_url = driver.current_url
        if "/login" in current_url:
            # قد يكون هناك نموذج إضافي
            try:
                # البحث عن زر Continue
                continue_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue')]")
                continue_btn.click()
                time.sleep(3)
            except:
                pass
            
            # التحقق مرة أخرى
            current_url = driver.current_url
            if "/login" in current_url:
                log("❌ فشل تسجيل الدخول")
                driver.quit()
                return None
        
        log("✅ تم تسجيل الدخول بنجاح!")
        
        # الحصول على الكوكيز
        cookies = driver.get_cookies()
        
        # تنظيف الكوكيز (إزالة الكوكيز غير الضرورية)
        important_cookies = []
        important_names = ['connect.sid', 'replit_session', 'user', 'csrftoken']
        
        for cookie in cookies:
            if cookie['name'] in important_names:
                important_cookies.append(cookie)
            elif 'replit' in cookie['domain']:
                important_cookies.append(cookie)
        
        if not important_cookies:
            # إذا لم يتم العثور على كوكيز مهمة، خذ كل الكوكيز
            important_cookies = cookies
        
        driver.quit()
        
        # تحديث وقت آخر تسجيل دخول
        last_login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log(f"✅ تم الحصول على {len(important_cookies)} كوكي")
        return important_cookies
    
    except TimeoutException:
        log("⏰ انتهى وقت التحميل")
        if driver:
            driver.quit()
        return None
    
    except Exception as e:
        log(f"❌ خطأ في تسجيل الدخول: {e}")
        if driver:
            try:
                driver.quit()
            except:
                pass
        return None


def get_webview_url():
    """الحصول على رابط Webview"""
    global last_webview_url, last_update_time
    
    # تحميل الكوكيز من الملف
    cookies = None
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r') as f:
                cookies = json.loads(f.read())
                log(f"📂 تم تحميل {len(cookies)} كوكي من الملف")
        except:
            pass
    
    # إذا لم توجد كوكيز، قم بتسجيل الدخول
    if not cookies:
        log("🔑 لا توجد كوكيز - جاري تسجيل الدخول...")
        cookies = login_to_replit()
        if cookies:
            save_cookies(cookies)
        else:
            log("❌ فشل تسجيل الدخول")
            return None
    
    # البحث عن الرابط
    if not os.path.exists(CHROMEDRIVER_PATH):
        log(f"❌ ChromeDriver غير موجود")
        return None
    
    driver = None
    try:
        # إعداد المتصفح
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1280,720')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        if os.path.exists(CHROMIUM_PATH):
            options.binary_location = CHROMIUM_PATH
        
        service = Service(executable_path=CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(45)
        
        # إضافة الكوكيز
        driver.get("https://replit.com")
        time.sleep(2)
        
        for cookie in cookies:
            try:
                if 'domain' not in cookie:
                    cookie['domain'] = '.replit.com'
                if 'path' not in cookie:
                    cookie['path'] = '/'
                driver.add_cookie(cookie)
            except Exception as e:
                pass
        
        log(f"📂 فتح المشروع...")
        driver.get(PROJECT_URL)
        time.sleep(5)
        
        # التحقق من الدخول
        if "login" in driver.current_url.lower():
            log("⚠️ الكوكيز منتهية - جاري تسجيل الدخول مجدداً...")
            driver.quit()
            
            # تسجيل الدخول مجدداً
            new_cookies = login_to_replit()
            if new_cookies:
                save_cookies(new_cookies)
                # محاولة مرة أخرى
                return get_webview_url()
            return None
        
        log("✅ تم الدخول إلى المشروع")
        
        # البحث عن زر Run
        try:
            run_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Run')]")
            run_btn.click()
            log("✅ تم الضغط على Run")
            time.sleep(5)
        except:
            log("⚠️ زر Run غير موجود أو المشروع يعمل بالفعل")
        
        # البحث عن Webview URL
        webview_url = None
        
        # البحث في iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            match = re.search(WEBVIEW_PATTERN, src)
            if match:
                webview_url = match.group(0)
                break
        
        # البحث في النص
        if not webview_url:
            page_source = driver.page_source
            matches = re.findall(WEBVIEW_PATTERN, page_source)
            if matches:
                webview_url = matches[0]
        
        driver.quit()
        
        if webview_url:
            last_webview_url = webview_url
            last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log(f"✅ الرابط: {webview_url}")
            
            # حفظ الرابط
            with open("webview_url.txt", "w") as f:
                f.write(f"{webview_url}\n")
                f.write(f"آخر تحديث: {last_update_time}\n")
            
            return webview_url
        else:
            log("⚠️ لم يتم العثور على رابط")
            return None
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        if driver:
            try:
                driver.quit()
            except:
                pass
        return None


def run_server():
    """تشغيل خادم HTTP"""
    try:
        server = HTTPServer(('0.0.0.0', KEEP_ALIVE_PORT), KeepAliveHandler)
        log(f"🌐 خادم HTTP يعمل على http://localhost:{KEEP_ALIVE_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"❌ خطأ في الخادم: {e}")


def main():
    global running
    
    log("🔥 بدء Keep Alive مع تسجيل دخول تلقائي")
    log(f"📧 البريد: {REPLIT_EMAIL}")
    log(f"⏱️ التحديث كل {REFRESH_INTERVAL} ثانية")
    
    if not SELENIUM_AVAILABLE:
        log("❌ Selenium غير مثبت!")
        return
    
    # تشغيل الخادم
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
    main()
