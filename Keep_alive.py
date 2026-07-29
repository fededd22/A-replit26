#!/usr/bin/env python3
"""
سكربت لتشغيل مشروع Replit مع Keep Alive - يحافظ على الجلسة نشطة مع إمكانية العمل المتزامن
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
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

COOKIE_FILE = "cookies.txt"
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL_SECONDS = 30  # زيادة إلى 30 ثانية لتقليل الحمل
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"
KEEP_ALIVE_PORT = 8080
PING_INTERVAL = 60  # ثانية


class KeepAliveHandler(BaseHTTPRequestHandler):
    """معالج طلبات HTTP لخدمة Keep Alive"""
    
    def do_GET(self):
        """معالجة طلبات GET"""
        parsed = urlparse(self.path)
        
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Keep Alive - Replit Session</title>
                <style>
                    body { font-family: Arial; text-align: center; padding: 50px; background: #0a0a0a; color: #00ff88; }
                    h1 { font-size: 3em; }
                    .status { font-size: 1.5em; margin: 20px 0; }
                    .time { color: #888; font-size: 0.8em; }
                    .success { color: #00ff88; }
                </style>
            </head>
            <body>
                <h1>🚀 Keep Alive Active</h1>
                <div class="status success">✅ الجلسة نشطة ومستمرة</div>
                <div class="time">تم التحديث: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</div>
                <br>
                <div>⏳ تشغيل المشروع بشكل مستمر</div>
                <div style="margin-top: 30px; font-size: 0.9em; color: #666;">
                    <p>📱 يمكنك العمل في ترمينال آخر أثناء تشغيل هذا السكربت</p>
                    <p>🔄 يتم إعادة تشغيل المشروع كل """ + str(REFRESH_INTERVAL_SECONDS) + """ ثانية</p>
                </div>
            </body>
            </html>
            """)
        elif parsed.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            status = f'{{"status": "running", "timestamp": "{datetime.now().isoformat()}", "interval": {REFRESH_INTERVAL_SECONDS}}}'
            self.wfile.write(status.encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def do_HEAD(self):
        """معالجة طلبات HEAD للـ Keep Alive"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
    
    def log_message(self, format, *args):
        """تعطيل تسجيل الطلبات لتجنب الفوضى"""
        pass


def run_keep_alive_server():
    """تشغيل خادم Keep Alive في خيط منفصل"""
    try:
        server = HTTPServer(('0.0.0.0', KEEP_ALIVE_PORT), KeepAliveHandler)
        log(f"🔌 خادم Keep Alive يعمل على المنفذ {KEEP_ALIVE_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"⚠️ خطأ في خادم Keep Alive: {e}")


def log(msg: str):
    """طباعة رسالة مع الطابع الزمني"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


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


def load_cookies_for_playwright():
    """تحميل الكوكيز من الملف"""
    if not os.path.exists(COOKIE_FILE):
        log(f"❌ ملف {COOKIE_FILE} مش موجود")
        return []
    
    jar = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        log(f"❌ خطأ في تحميل الكوكيز: {e}")
        return []
    
    cookies = [netscape_cookie_to_playwright(c) for c in jar]
    log(f"✅ تم تحميل {len(cookies)} كوكي")
    return cookies


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
    """تشغيل دورة واحدة فقط"""
    log("🚀 بدء دورة جديدة")
    
    cookies = load_cookies_for_playwright()
    if not cookies:
        log("❌ لا توجد كوكيز")
        return False

    webview_url = None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_cookies(cookies)
        page = context.new_page()

        log(f"📂 فتح المشروع")
        page.goto(PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        if "/login" in page.url:
            log("❌ الكوكيز منتهية")
            browser.close()
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


def main():
    """الحلقة الرئيسية مع Keep Alive"""
    log("🔥 بدء التشغيل مع Keep Alive")
    log(f"⏱️ سيتم إعادة التشغيل كل {REFRESH_INTERVAL_SECONDS} ثانية")
    log(f"🌐 خادم Keep Alive على المنفذ {KEEP_ALIVE_PORT}")
    log("📌 يمكنك فتح ترمينال آخر للعمل بشكل طبيعي")
    
    # تشغيل خادم Keep Alive في خيط منفصل
    keep_alive_thread = threading.Thread(target=run_keep_alive_server, daemon=True)
    keep_alive_thread.start()
    
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
