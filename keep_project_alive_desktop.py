#!/usr/bin/env python3
"""
سكربت لسيرفر/ترمينال - يشغل مشروع Replit ويفتح رابط الـ Webview تلقائياً.
"""

import sys
import time
import http.cookiejar
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

COOKIE_FILE = "cookies.txt"
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL_SECONDS = 10
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
    يستخرج رابط الـ Webview (replit.dev) من صفحة المشروع.
    """
    # طريقة 1: البحث في عنصر iframe الخاص بالـ Webview
    try:
        # البحث عن iframe الذي يحتوي على رابط replit.dev
        iframes = page.locator("iframe[src*='replit.dev']").all()
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            match = re.search(WEBVIEW_PATTERN, src)
            if match:
                return match.group(0)
    except Exception as e:
        log(f"⚠️ طريقة iframe فشلت: {e}")
    
    # طريقة 2: البحث في عناصر الصفحة عن الرابط
    try:
        # البحث عن أي عنصر يحتوي على رابط replit.dev
        elements = page.locator("[href*='replit.dev'], [src*='replit.dev']").all()
        for el in elements:
            href = el.get_attribute("href") or ""
            src = el.get_attribute("src") or ""
            text = el.text_content() or ""
            
            # البحث في href أو src أو النص
            for content in [href, src, text]:
                match = re.search(WEBVIEW_PATTERN, content)
                if match:
                    return match.group(0)
    except Exception as e:
        log(f"⚠️ طريقة العناصر فشلت: {e}")
    
    # طريقة 3: استخدام JavaScript لاستخراج الرابط من الـ Webview
    try:
        js_result = page.evaluate("""
            () => {
                // البحث في كل iframe
                const iframes = document.querySelectorAll('iframe');
                for (let iframe of iframes) {
                    const src = iframe.src || '';
                    if (src.includes('replit.dev')) {
                        return src;
                    }
                }
                
                // البحث في الروابط
                const links = document.querySelectorAll('a[href*="replit.dev"]');
                for (let link of links) {
                    return link.href;
                }
                
                // البحث في النص
                const body = document.body.innerText || '';
                const match = body.match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                if (match) {
                    return match[0];
                }
                
                return null;
            }
        """)
        if js_result and js_result != "null":
            return js_result
    except Exception as e:
        log(f"⚠️ طريقة JavaScript فشلت: {e}")
    
    return None


def ensure_project_running(page):
    """
    يضغط على زر Run إذا كان المشروع متوقفاً.
    """
    # انتظر تحميل الصفحة
    page.wait_for_timeout(5000)
    
    # التحقق من حالة المشروع أولاً
    try:
        # البحث عن زر Stop (يعني شغال)
        stop_btn = page.locator("button:has-text('Stop')").first
        if stop_btn.count() > 0 and stop_btn.is_visible(timeout=2000):
            log("✅ المشروع شغال بالفعل")
            return True
    except:
        pass
    
    # محاولة الضغط على زر Run بطرق متعددة
    methods = [
        # طريقة النص
        lambda: page.locator("button:has-text('Run')").first,
        # طريقة aria-label
        lambda: page.locator("button[aria-label*='Run' i]").first,
        # طريقة data-testid
        lambda: page.locator("[data-testid='run-button'], [data-cy='run-button']").first,
        # طريقة أيقونة play
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
                    log("🟢 تم الضغط على زر Run - المشروع بدأ بالتشغيل.")
                    page.wait_for_timeout(8000)  # انتظر حتى يبدأ المشروع
                    return True
        except:
            continue
    
    # محاولة باستخدام JavaScript
    try:
        result = page.evaluate("""
            () => {
                const buttons = document.querySelectorAll('button');
                for (let btn of buttons) {
                    const text = (btn.textContent || '').toLowerCase();
                    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                    if (text.includes('run') || label.includes('run')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        if result:
            log("🟢 تم الضغط على زر Run (عن طريق JavaScript).")
            page.wait_for_timeout(8000)
            return True
    except:
        pass
    
    log("⚠️ لم أجد زر Run - قد يكون المشروع شغالاً بالفعل.")
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

        # تحقق من تسجيل الدخول
        if "/login" in page.url:
            log("⚠️ الكوكيز منتهية - الصفحة رجّعت لتسجيل الدخول.")
            log("📌 صدّر cookies.txt جديد وحاول تاني.")
            browser.close()
            sys.exit(1)

        log("✅ تم الدخول على المشروع بنجاح.")
        
        # تشغيل المشروع
        ensure_project_running(page)
        
        # استخراج رابط الـ Webview
        log("🔍 جاري البحث عن رابط الـ Webview...")
        webview_url = get_webview_url(page)
        
        if webview_url:
            log(f"🌐 رابط الـ Webview: {webview_url}")
            log("📋 يمكنك استخدام هذا الرابط للوصول إلى خدمة V2Ray/VLESS")
            
            # نسخ الرابط إلى ملف للاستخدام الخارجي
            with open("webview_url.txt", "w") as f:
                f.write(webview_url)
            log("💾 تم حفظ الرابط في ملف webview_url.txt")
        else:
            log("⚠️ لم أجد رابط الـ Webview - قد يكون المشروع لم يبدأ بالكامل بعد.")
            log("🔄 سيتم المحاولة مرة أخرى في التحديث التالي...")

        log(f"🔄 هيتم تحديث الصفحة كل {REFRESH_INTERVAL_SECONDS} ثانية...")

        try:
            while True:
                time.sleep(REFRESH_INTERVAL_SECONDS)
                
                # إعادة تحميل الصفحة
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                
                # تحقق من الجلسة
                if "/login" in page.url:
                    log("❌ الجلسة انتهت - محتاج كوكيز جديدة.")
                    break
                
                # تأكد أن المشروع شغال
                ensure_project_running(page)
                
                # حاول استخراج رابط الـ Webview مرة أخرى (إذا لم نجده سابقاً)
                if not webview_url:
                    webview_url = get_webview_url(page)
                    if webview_url:
                        log(f"🌐 تم العثور على رابط الـ Webview: {webview_url}")
                        with open("webview_url.txt", "w") as f:
                            f.write(webview_url)
                
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log(f"✅ تم التحديث - {now}")
                
        except KeyboardInterrupt:
            log("⏹️ تم الإيقاف يدويًا.")

        browser.close()


if __name__ == "__main__":
    main()
