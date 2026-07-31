#!/usr/bin/env python3
"""
سكربت مدمج لتشغيل Replit و Google Cloud Shell مع Keep Alive
يحافظ على الجلسات نشطة مع إمكانية العمل المتزامن
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

# ==================== إعدادات Replit ====================
REPLIT_COOKIE_FILE = "cookies.txt"
REPLIT_PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REPLIT_REFRESH_INTERVAL = 10
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"

# ==================== إعدادات Google Cloud Shell ====================
GOOGLE_COOKIE_FILE = "cookies_google.txt"
GOOGLE_PROJECT_URL = "https://shell.cloud.google.com/"
GOOGLE_REFRESH_INTERVAL = 20

# ==================== إعدادات عامة ====================
KEEP_ALIVE_PORT = 8080
PING_INTERVAL = 60

# ==================== بيانات تسجيل الدخول لـ Replit ====================
REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"

# متغيرات عامة
last_webview_url = None
last_update_time = None
last_google_status = None
last_google_update = None
running = True


class KeepAliveHandler(BaseHTTPRequestHandler):
    """معالج طلبات HTTP لخدمة Keep Alive"""
    
    def do_GET(self):
        """معالجة طلبات GET"""
        parsed = urlparse(self.path)
        
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta http-equiv="refresh" content="30">
                <title>Keep Alive - Replit & Google</title>
                <style>
                    body {{ font-family: Arial; text-align: center; padding: 50px; background: #0a0a0a; color: #00ff88; }}
                    h1 {{ font-size: 2.5em; }}
                    .status {{ font-size: 1.5em; margin: 20px 0; }}
                    .time {{ color: #888; font-size: 0.8em; }}
                    .success {{ color: #00ff88; }}
                    .info {{ color: #666; font-size: 0.9em; margin: 10px 0; }}
                    .box {{ background: #1a1a2e; padding: 20px; border-radius: 10px; margin: 20px 0; border: 1px solid #333; }}
                    .box-title {{ color: #00ccff; font-size: 1.2em; margin-bottom: 10px; }}
                    .google-status {{ color: {'#00ff88' if last_google_status == 'running' else '#ff8800'}; }}
                    .replit-status {{ color: {'#00ff88' if last_webview_url else '#ff8800'}; }}
                </style>
            </head>
            <body>
                <h1>🚀 Keep Alive Active</h1>
                <div class="status success">✅ الجلسات نشطة ومستمرة</div>
                <div class="time">تم التحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                
                <div class="box">
                    <div class="box-title">🔄 Replit</div>
                    <div class="replit-status">🌐 {last_webview_url or '⏳ جاري البحث...'}</div>
                    <div class="time">آخر تحديث: {last_update_time or 'لم يتم التحديث'}</div>
                    <div style="margin-top: 10px; color: #666;">⏱️ كل {REPLIT_REFRESH_INTERVAL} ثانية</div>
                </div>
                
                <div class="box">
                    <div class="box-title">☁️ Google Cloud Shell</div>
                    <div class="google-status">📊 الحالة: {last_google_status or '⏳ في انتظار التشغيل'}</div>
                    <div class="time">آخر تحديث: {last_google_update or 'لم يتم التحديث'}</div>
                    <div style="margin-top: 10px; color: #666;">⏱️ كل {GOOGLE_REFRESH_INTERVAL} ثانية</div>
                </div>
                
                <div style="margin-top: 30px; font-size: 0.9em; color: #666;">
                    <p>📱 يمكنك العمل في ترمينال آخر أثناء تشغيل هذا السكربت</p>
                    <p>📁 ملفات الكوكيز: {REPLIT_COOKIE_FILE} (Replit) | {GOOGLE_COOKIE_FILE} (Google)</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode('utf-8'))
            
        elif parsed.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            status = {
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "replit": {
                    "webview_url": last_webview_url,
                    "last_update": last_update_time,
                    "interval": REPLIT_REFRESH_INTERVAL
                },
                "google": {
                    "status": last_google_status,
                    "last_update": last_google_update,
                    "interval": GOOGLE_REFRESH_INTERVAL
                }
            }
            self.wfile.write(json.dumps(status).encode('utf-8'))
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


def log(msg: str):
    """طباعة رسالة مع الطابع الزمني"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ==================== دوال Replit ====================

def netscape_cookie_to_playwright(cookie) -> dict:
    """تحويل الكوكيز إلى صيغة Playwright"""
    pw_cookie = {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path or "/",
        "secure": bool(cookie.secure),
        "httpOnly": bool(cookie._rest.get("HttpOnly", False)) if hasattr(cookie, "_rest") else False,
    }
    if cookie.expires:
        pw_cookie["expires"] = cookie.expires
    return pw_cookie


def load_cookies_for_playwright(cookie_file):
    """تحميل الكوكيز من ملف"""
    if not os.path.exists(cookie_file):
        log(f"❌ ملف {cookie_file} غير موجود")
        return []
    
    jar = http.cookiejar.MozillaCookieJar(cookie_file)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        log(f"❌ خطأ في تحميل الكوكيز من {cookie_file}: {e}")
        return []
    
    cookies = [netscape_cookie_to_playwright(c) for c in jar]
    log(f"✅ تم تحميل {len(cookies)} كوكي من {cookie_file}")
    return cookies


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


def login_to_replit():
    """تسجيل الدخول إلى Replit والحصول على كوكيز جديدة"""
    log("🔑 تسجيل الدخول إلى Replit...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
                with open(REPLIT_COOKIE_FILE, 'w') as f:
                    json.dump(cleaned_cookies, f, indent=2)
                log(f"✅ تم حفظ {len(cleaned_cookies)} كوكي لـ Replit")
                return True
            else:
                log("❌ لم يتم الحصول على كوكيز صالحة")
                return False
    
    except Exception as e:
        log(f"❌ خطأ في تسجيل الدخول: {e}")
        return False


def press_run_button_with_retry(page, max_attempts=10):
    """محاولات للضغط على زر Run في Replit"""
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
    """استخراج رابط Webview من Replit"""
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


def run_replit_once():
    """تشغيل دورة واحدة لـ Replit"""
    global last_webview_url, last_update_time
    
    log("🔄 بدء دورة Replit")
    
    # محاولة تسجيل الدخول إذا لم يكن هناك كوكيز
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log("📂 لا يوجد ملف كوكيز Replit - جاري تسجيل الدخول...")
        if not login_to_replit():
            log("❌ فشل تسجيل الدخول إلى Replit")
            return False
    
    cookies = load_cookies_for_playwright(REPLIT_COOKIE_FILE)
    if not cookies:
        log("❌ لا توجد كوكيز Replit - محاولة تسجيل الدخول...")
        if login_to_replit():
            cookies = load_cookies_for_playwright(REPLIT_COOKIE_FILE)
        if not cookies:
            return False

    webview_url = None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
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
                log("❌ لا توجد كوكيز صالحة لـ Replit")
                browser.close()
                return False
            
            page = context.new_page()

            log(f"📂 فتح مشروع Replit")
            page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            if "/login" in page.url:
                log("❌ كوكيز Replit منتهية - جاري تسجيل الدخول...")
                browser.close()
                if login_to_replit():
                    return run_replit_once()
                return False

            log("✅ تم الدخول إلى مشروع Replit")

            # تشغيل المشروع
            if press_run_button_with_retry(page, max_attempts=10):
                log("✅ تم تشغيل مشروع Replit")
            else:
                log("⚠️ فشل تشغيل مشروع Replit")

            # البحث عن رابط Webview
            for attempt in range(5):
                webview_url = get_webview_url(page)
                if webview_url:
                    break
                page.wait_for_timeout(2000)

            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ في Replit: {e}")
        return False
    
    # حفظ الرابط
    if webview_url:
        last_webview_url = webview_url
        last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log(f"🌐 رابط Webview: {webview_url}")
        with open("webview_url.txt", "w") as f:
            f.write(f"{webview_url}\n")
            f.write(f"التحديث: {last_update_time}\n")
        return True
    else:
        log("⚠️ لم يتم العثور على رابط Webview")
        return False


# ==================== دوال Google Cloud Shell ====================

def check_login_status(page):
    """التحقق من حالة تسجيل الدخول إلى Google"""
    try:
        user_elements = page.locator("[data-email], [aria-label*='Account'], .user-email").all()
        if user_elements:
            return True
        
        login_btn = page.locator("a:has-text('Sign in'), button:has-text('Sign in')").first
        if login_btn.count() > 0 and login_btn.is_visible(timeout=1000):
            return False
        
        avatar = page.locator("img[aria-label*='Account'], .avatar, .user-profile").first
        if avatar.count() > 0 and avatar.is_visible(timeout=1000):
            return True
            
        return True
    except:
        return True


def activate_shell(page):
    """تشغيل Cloud Shell"""
    log("🔍 جاري البحث عن زر تفعيل Cloud Shell...")
    
    for attempt in range(8):
        page.wait_for_timeout(1500)
        
        selectors = [
            "button:has-text('Activate Cloud Shell')",
            "button:has-text('Open Cloud Shell')",
            "button:has-text('Start Cloud Shell')",
            "button[aria-label*='Cloud Shell']",
            "button:has-text('activate')",
            "button:has-text('shell')",
            "button:has(svg[viewBox*='terminal'])",
            "button:has(svg[viewBox*='shell'])",
            "button[class*='shell']",
            "button[class*='cloud-shell']",
            "button[data-testid*='shell']",
            "button[data-testid*='cloud']",
            "button[aria-label*='shell']",
            "button[aria-label*='terminal']",
            "button:has-text('>_')",
            "button:has-text('$_')",
            "button:has-text('console')",
            "button:has-text('▶')",
            "button:has-text('▼')",
            "[role='button']:has-text('Cloud Shell')",
        ]
        
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    log(f"✅ تم العثور على زر Cloud Shell: {selector}")
                    btn.click()
                    log("🟢 تم تفعيل Cloud Shell")
                    page.wait_for_timeout(5000)
                    return True
            except:
                continue
        
        if attempt < 7:
            log(f"⚠️ محاولة {attempt + 1}/8...")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
    
    return False


def get_shell_status(page):
    """التحقق من حالة Cloud Shell"""
    try:
        indicators = [
            "iframe[src*='cloud-shell']",
            "iframe[title*='Cloud Shell']",
            "div[class*='terminal']",
            "div[class*='console']",
            "div[aria-label*='Cloud Shell']",
            "div[aria-label*='terminal']",
        ]
        
        for selector in indicators:
            try:
                el = page.locator(selector).first
                if el.count() > 0 and el.is_visible(timeout=1000):
                    return "running"
            except:
                continue
        
        stop_btn = page.locator("button:has-text('Stop Cloud Shell'), button:has-text('Close Cloud Shell'), button[aria-label*='close shell']").first
        if stop_btn.count() > 0 and stop_btn.is_visible(timeout=1000):
            return "running"
        
        return "stopped"
    except:
        return "unknown"


def run_google_once():
    """تشغيل دورة واحدة لـ Google Cloud Shell"""
    global last_google_status, last_google_update
    
    log("🔄 بدء دورة Google Cloud Shell")
    
    cookies = load_cookies_for_playwright(GOOGLE_COOKIE_FILE)
    if not cookies:
        log("❌ لا توجد كوكيز Google - قم بتصدير كوكيز Google")
        last_google_status = "no_cookies"
        last_google_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (Chrome, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            context.add_cookies(cookies)
            page = context.new_page()

            log(f"📂 فتح Google Cloud Shell")
            page.goto(GOOGLE_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            # التحقق من تسجيل الدخول
            if not check_login_status(page):
                log("❌ غير مسجل دخول Google - قم بتحديث الكوكيز")
                last_google_status = "not_logged_in"
                last_google_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                browser.close()
                return False

            log("✅ تم تسجيل الدخول إلى Google")

            # التحقق من حالة Shell
            status = get_shell_status(page)
            log(f"📊 حالة Cloud Shell: {status}")
            last_google_status = status

            # تفعيل Shell إذا كان متوقفاً
            if status == "stopped":
                if activate_shell(page):
                    log("✅ تم تفعيل Cloud Shell")
                    last_google_status = "activated"
                else:
                    log("⚠️ فشل في تفعيل Cloud Shell")
                    last_google_status = "activation_failed"
            else:
                log("✅ Cloud Shell يعمل بالفعل")

            last_google_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # البحث عن رابط Shell
            shell_url = None
            try:
                iframes = page.locator("iframe[src*='cloud-shell'], iframe[src*='shell']").all()
                for iframe in iframes:
                    src = iframe.get_attribute("src") or ""
                    if src:
                        shell_url = src
                        break
            except:
                pass

            browser.close()

            # حفظ المعلومات
            with open("google_shell_status.txt", "w") as f:
                f.write(f"آخر تحديث: {last_google_update}\n")
                f.write(f"الحالة: {last_google_status}\n")
                if shell_url:
                    f.write(f"رابط Shell: {shell_url}\n")

            return True
    
    except Exception as e:
        log(f"❌ خطأ في Google Cloud Shell: {e}")
        last_google_status = "error"
        last_google_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    """الحلقة الرئيسية المدمجة"""
    global running
    
    log("🔥 بدء التشغيل المدمج لـ Replit و Google Cloud Shell")
    log(f"📁 ملف كوكيز Replit: {REPLIT_COOKIE_FILE}")
    log(f"📁 ملف كوكيز Google: {GOOGLE_COOKIE_FILE}")
    log(f"⏱️ Replit: كل {REPLIT_REFRESH_INTERVAL} ثانية")
    log(f"⏱️ Google: كل {GOOGLE_REFRESH_INTERVAL} ثانية")
    log(f"🌐 خادم Keep Alive على المنفذ {KEEP_ALIVE_PORT}")
    log("📌 يمكنك فتح ترمينال آخر للعمل بشكل طبيعي")
    
    # تشغيل خادم Keep Alive في خيط منفصل
    keep_alive_thread = threading.Thread(target=run_keep_alive_server, daemon=True)
    keep_alive_thread.start()
    
    # متغيرات لتتبع وقت التشغيل
    replit_counter = 0
    google_counter = 0
    
    # بدء الحلقة الرئيسية
    while running:
        try:
            # تشغيل Google Cloud Shell كل 10 ثواني
            if google_counter % 1 == 0:  # كل دورة
                run_google_once()
            
            # تشغيل Replit كل 30 ثانية (3 دورات من Google)
            if replit_counter % 3 == 0:  # كل 3 دورات (30 ثانية)
                run_replit_once()
            
            google_counter += 1
            replit_counter += 1
            
            # الانتظار 10 ثواني
            log(f"⏳ الانتظار 10 ثواني...")
            for i in range(10, 0, -1):
                if i % 5 == 0 or i <= 3:
                    log(f"⏳ {i}s")
                time.sleep(1)
            
            log("🔄 بدء دورة جديدة...")
            print("-" * 50)
            
        except KeyboardInterrupt:
            log("⏹️ تم الإيقاف")
            running = False
            break
        except Exception as e:
            log(f"❌ خطأ: {e}")
            time.sleep(3)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    main()
