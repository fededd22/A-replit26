#!/usr/bin/env python3
"""
سكربت لتشغيل مشروع Replit وإعادة تشغيل نفسه كل 40 ثانية
"""

import sys
import time
import http.cookiejar
import re
import os
import subprocess
from datetime import datetime

COOKIE_FILE = "cookies.txt"
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL_SECONDS = 40  # كل 40 ثانية
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"
SCRIPT_NAME = "keep_project_alive_desktop.py"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def netscape_cookie_to_playwright(cookie) -> dict:
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
    jar = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        log(f"❌ ملف {COOKIE_FILE} مش موجود")
        return []
    cookies = [netscape_cookie_to_playwright(c) for c in jar]
    log(f"تم تحميل {len(cookies)} كوكي")
    return cookies


def press_run_button_with_retry(page, max_attempts=5):
    """محاولات للضغط على زر Run"""
    log("🔍 جاري البحث عن زر Run...")
    
    for attempt in range(max_attempts):
        page.wait_for_timeout(1500)
        
        selectors = [
            "button:has-text('Run')",
            "button:has-text('Run') >> visible=true",
            "button[aria-label='Run']",
            "button[aria-label*='Run' i]",
            "[data-testid='run-button']",
            "[data-cy='run-button']",
            "button[data-testid='run-button']",
            ".run-button",
            "button[class*='run']",
            "button:has(svg[viewBox*='play'])",
            "button:has(svg[data-icon='play'])",
            "button:has(span:has-text('Run'))",
            "header button:has-text('Run')",
        ]
        
        for selector in selectors:
            try:
                buttons = page.locator(selector).all()
                for btn in buttons:
                    if btn.is_visible(timeout=1000):
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
            stop_btn = page.locator("button:has-text('Stop')")
            if stop_btn.count() > 0 and stop_btn.first.is_visible(timeout=2000):
                log("✅ المشروع شغال بالفعل")
                return True
        except:
            pass
        
        if attempt < max_attempts - 1:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
    
    return False


def get_webview_url(page):
    """استخراج رابط Webview"""
    log("🔍 البحث عن رابط Webview...")
    
    for attempt in range(5):
        page.wait_for_timeout(1500)
        
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
                log(f"✅ تم العثور على رابط Webview في النص: {url}")
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


def restart_script():
    """إعادة تشغيل السكربت نفسه"""
    log("🔄 جاري إعادة تشغيل السكربت...")
    try:
        # تشغيل السكربت نفسه في عملية جديدة
        subprocess.Popen(["python", SCRIPT_NAME])
        log("✅ تم إعادة تشغيل السكربت")
        sys.exit(0)  # إنهاء العملية الحالية
    except Exception as e:
        log(f"❌ فشل إعادة التشغيل: {e}")
        sys.exit(1)


def main():
    log("🚀 بدء تشغيل السكربت")
    
    cookies = load_cookies_for_playwright()
    if not cookies:
        log("❌ لا توجد كوكيز صالحة - تأكد من وجود cookies.txt")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (Chrome, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_cookies(cookies)
        page = context.new_page()

        log(f"📂 فتح المشروع: {PROJECT_URL}")
        page.goto(PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        if "/login" in page.url:
            log("❌ الكوكيز منتهية - الرجاء تحديث cookies.txt")
            browser.close()
            sys.exit(1)

        log("✅ تم الدخول إلى المشروع")

        # تشغيل المشروع
        if press_run_button_with_retry(page, max_attempts=5):
            log("✅ تم تشغيل المشروع بنجاح!")
        else:
            log("⚠️ فشل تشغيل المشروع - قد يكون شغالاً بالفعل")

        # البحث عن رابط Webview
        webview_url = get_webview_url(page)
        
        if webview_url:
            log(f"🌐 رابط Webview: {webview_url}")
            # حفظ الرابط في ملف للاستخدام الخارجي
            with open("webview_url.txt", "w") as f:
                f.write(f"{webview_url}\n")
                f.write(f"آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            log("💾 تم حفظ الرابط في webview_url.txt")
            
            # طباعة الرابط بشكل مميز
            print("\n" + "="*60)
            print(f"🌐 رابط Webview: {webview_url}")
            print("="*60 + "\n")
        else:
            log("⚠️ لم يتم العثور على رابط Webview")

        # الانتظار 40 ثانية ثم إعادة التشغيل
        log(f"⏳ الانتظار {REFRESH_INTERVAL_SECONDS} ثانية قبل إعادة التشغيل...")
        
        # عد تنازلي
        for i in range(REFRESH_INTERVAL_SECONDS, 0, -10):
            if i % 10 == 0:
                log(f"⏳ {i} ثانية متبقية...")
            time.sleep(10)

        browser.close()
        
        # إعادة تشغيل السكربت
        restart_script()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("⏹️ تم الإيقاف يدوياً")
        sys.exit(0)
    except Exception as e:
        log(f"❌ خطأ غير متوقع: {e}")
        # محاولة إعادة التشغيل حتى في حالة الخطأ
        log("🔄 محاولة إعادة التشغيل بعد الخطأ...")
        time.sleep(5)
        restart_script()