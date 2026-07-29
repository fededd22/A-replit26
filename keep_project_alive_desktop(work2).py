#!/usr/bin/env python3
"""
سكربت لسيرفر/ترمينال - يشغل مشروع Replit ويستخرج رابط الـ Webview الصحيح.
"""

import sys
import time
import http.cookiejar
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

COOKIE_FILE = "cookies.txt"
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL_SECONDS = 30
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"


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
        log(f"❌ ملف {COOKIE_FILE} مش موجود في نفس المجلد. وقفت.")
        sys.exit(1)
    cookies = [netscape_cookie_to_playwright(c) for c in jar]
    log(f"تم تحميل {len(cookies)} كوكي من {COOKIE_FILE}.")
    return cookies


def get_webview_url(page) -> str:
    """
    يستخرج رابط الـ Webview الحقيقي (بدون المسارات الإضافية).
    """
    # طريقة 1: البحث في عنصر iframe الخاص بالـ Webview
    try:
        iframes = page.locator("iframe[src*='replit.dev']").all()
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            # استخراج الرابط الأساسي فقط (بدون /_repl.co/...)
            match = re.search(WEBVIEW_PATTERN, src)
            if match:
                clean_url = match.group(0)
                log(f"✅ تم العثور على رابط Webview من iframe: {clean_url}")
                return clean_url
    except Exception as e:
        log(f"⚠️ طريقة iframe فشلت: {e}")
    
    # طريقة 2: البحث في console/logs عن رابط الخدمة
    try:
        # البحث في عناصر console/output
        console_elements = page.locator("[class*='console'], [class*='output'], [class*='terminal'], [class*='log']").all()
        for el in console_elements:
            text = el.text_content() or ""
            # البحث عن رابط يشبه replit.dev:5000
            matches = re.findall(WEBVIEW_PATTERN, text)
            for match in matches:
                if match and "replit.dev" in match:
                    log(f"✅ تم العثور على رابط Webview من console: {match}")
                    return match
    except Exception as e:
        log(f"⚠️ طريقة console فشلت: {e}")
    
    # طريقة 3: استخدام JavaScript لاستخراج الرابط
    try:
        js_result = page.evaluate("""
            () => {
                // البحث في كل iframe
                const iframes = document.querySelectorAll('iframe');
                for (let iframe of iframes) {
                    const src = iframe.src || '';
                    const match = src.match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                    if (match) {
                        return match[0];
                    }
                }
                
                // البحث في الروابط
                const links = document.querySelectorAll('a[href*="replit.dev"]');
                for (let link of links) {
                    const match = link.href.match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                    if (match) {
                        return match[0];
                    }
                }
                
                // البحث في نص الصفحة
                const body = document.body.innerText || '';
                const match = body.match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                if (match) {
                    return match[0];
                }
                
                return null;
            }
        """)
        if js_result and js_result != "null":
            log(f"✅ تم العثور على رابط Webview من JavaScript: {js_result}")
            return js_result
    except Exception as e:
        log(f"⚠️ طريقة JavaScript فشلت: {e}")
    
    return None


def press_run_button(page):
    """يضغط على زر Run إذا كان المشروع متوقفاً."""
    page.wait_for_timeout(5000)
    
    # التحقق من حالة المشروع
    try:
        stop_btn = page.locator("button:has-text('Stop')").first
        if stop_btn.count() > 0 and stop_btn.is_visible(timeout=2000):
            return True
    except:
        pass
    
    # محاولات الضغط على زر Run
    methods = [
        lambda: page.locator("button:has-text('Run')").first,
        lambda: page.locator("button[aria-label*='Run' i]").first,
        lambda: page.locator("[data-testid='run-button'], [data-cy='run-button']").first,
        lambda: page.locator("button:has(svg[viewBox*='play' i])").first,
    ]
    
    for method in methods:
        try:
            btn = method()
            if btn.count() > 0 and btn.is_visible(timeout=2000):
                btn_text = btn.text_content() or ""
                btn_label = btn.get_attribute("aria-label") or ""
                if "Run" in btn_text or "run" in btn_text.lower() or "run" in btn_label.lower():
                    btn.click()
                    log("🟢 تم الضغط على زر Run.")
                    page.wait_for_timeout(8000)
                    return True
        except:
            continue
    
    return False


def main():
    cookies = load_cookies_for_playwright()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_cookies(cookies)

        page = context.new_page()

        log(f"فتح المشروع: {PROJECT_URL}")
        page.goto(PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        if "/login" in page.url:
            log("⚠️ الكوكيز منتهية - الصفحة رجّعت لتسجيل الدخول.")
            log("📌 صدّر cookies.txt جديد وحاول تاني.")
            browser.close()
            sys.exit(1)

        log("✅ تم الدخول على المشروع بنجاح.")
        
        # تشغيل المشروع
        if press_run_button(page):
            log("✅ تم تشغيل المشروع.")
        else:
            log("⚠️ المشروع قد يكون شغالاً بالفعل.")
        
        # استخراج رابط الـ Webview
        webview_url = None
        for attempt in range(5):  # 5 محاولات
            log(f"🔍 محاولة {attempt + 1}/5 للعثور على رابط Webview...")
            webview_url = get_webview_url(page)
            if webview_url:
                break
            page.wait_for_timeout(3000)
        
        if webview_url:
            # التأكد من أن الرابط صحيح (بدون مسارات إضافية)
            clean_match = re.search(WEBVIEW_PATTERN, webview_url)
            if clean_match:
                webview_url = clean_match.group(0)
            
            log(f"🌐 رابط الـ Webview الصحيح: {webview_url}")
            log("📋 يمكنك استخدام هذا الرابط للوصول إلى خدمة V2Ray/VLESS")
            
            with open("webview_url.txt", "w") as f:
                f.write(webview_url)
            log("💾 تم حفظ الرابط في ملف webview_url.txt")
        else:
            log("⚠️ لم أجد رابط الـ Webview.")

        log(f"🔄 تحديث الصفحة كل {REFRESH_INTERVAL_SECONDS} ثانية...")

        try:
            while True:
                time.sleep(REFRESH_INTERVAL_SECONDS)
                
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                
                if "/login" in page.url:
                    log("❌ الجلسة انتهت - محتاج كوكيز جديدة.")
                    break
                
                # التأكد من تشغيل المشروع
                if press_run_button(page):
                    log("✅ المشروع شغال")
                
                # إعادة استخراج الرابط إذا لم يكن موجوداً
                if not webview_url:
                    webview_url = get_webview_url(page)
                    if webview_url:
                        clean_match = re.search(WEBVIEW_PATTERN, webview_url)
                        if clean_match:
                            webview_url = clean_match.group(0)
                        log(f"🌐 تم العثور على رابط Webview: {webview_url}")
                        with open("webview_url.txt", "w") as f:
                            f.write(webview_url)
                
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log(f"✅ تم التحديث - {now}")
                
        except KeyboardInterrupt:
            log("⏹️ تم الإيقاف يدويًا.")

        browser.close()


if __name__ == "__main__":
    main()
