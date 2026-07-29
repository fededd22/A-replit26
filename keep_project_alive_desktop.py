#!/usr/bin/env python3
"""
سكربت لكمبيوتر حقيقي (ويندوز/لينكس/ماك) - مش للموبايل.

بيستخدم Playwright عشان يفتح متصفح Chromium حقيقي، يحمّل الكوكيز بتاعتك
من cookies.txt، يدخل مباشرة على صفحة المشروع في ريبلت وهو مسجل دخول
تلقائيًا، ويضغط زرار Run تلقائيًا عشان يشغّله، وبعدين يعمل تحديث (reload)
للصفحة كل 30 ثانية باستمرار.
"""

import sys
import time
import http.cookiejar
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

COOKIE_FILE = "cookies.txt"
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL_SECONDS = 30


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def netscape_cookie_to_playwright(cookie) -> dict:
    """يحوّل كوكي من صيغة http.cookiejar لصيغة Playwright."""
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


def ensure_project_running(page):
    """
    يبحث عن زر Run في واجهة Replit ويضغط عليه إذا كان المشروع متوقفاً.
    """
    # قائمة بمحددات محتملة لزر Run في واجهة Replit
    selectors = [
        # الطريقة الأكثر دقة - زر Run في شريط الأدوات
        "button[aria-label='Run']",
        "button[data-testid='run-button']",
        "button:has-text('Run')",
        "button:has-text('run')",
        # زر Run في واجهة Replit الجديدة
        "button[class*='Run']",
        "button[class*='run']",
        "div[class*='run'] button",
        # محددات عامة
        "button:has(svg[viewBox*='play'])",
        "button:has(svg[data-icon='play'])",
        # زر Run في حالة المشروع متوقف (يظهر نص "Run")
        "button:has-text('Run') >> visible=true",
        # محاولة العثور على أي زر به أيقونة تشغيل
        "button[aria-label*='run' i]",
        "button[aria-label*='Run' i]",
        # في بعض الأحيان يكون الزر داخل عنصر آخر
        "[data-cy='run-button']",
        ".run-button",
        "#run-button",
    ]
    
    # انتظر قليلاً حتى تتحمّل الصفحة بالكامل
    page.wait_for_timeout(3000)
    
    # حاول البحث عن الزر بعدة طرق
    for selector in selectors:
        try:
            button = page.locator(selector).first
            if button.count() > 0 and button.is_visible(timeout=2000):
                # تحقق إذا كان الزر مكتوباً عليه "Run" (يعني المشروع متوقف)
                button_text = button.text_content() or ""
                if "Run" in button_text or "run" in button_text:
                    button.click()
                    log("🟢 تم الضغط على زر Run - المشروع بدأ بالتشغيل.")
                    page.wait_for_timeout(5000)  # انتظر حتى يبدأ المشروع
                    return True
                # في بعض الأحيان الزر يكون عبارة عن أيقونة فقط
                elif button.get_attribute("aria-label") and "run" in button.get_attribute("aria-label").lower():
                    button.click()
                    log("🟢 تم الضغط على زر Run (عن طريق aria-label).")
                    page.wait_for_timeout(5000)
                    return True
        except Exception as e:
            continue
    
    # محاولة أخيرة: البحث عن أي زر به أيقونة play
    try:
        play_button = page.locator("button:has(svg)").filter(
            has_text="Run"
        ).first
        if play_button.count() > 0 and play_button.is_visible(timeout=2000):
            play_button.click()
            log("🟢 تم الضغط على زر Run (آخر محاولة).")
            page.wait_for_timeout(5000)
            return True
    except:
        pass
    
    # إذا لم نجد الزر، نتحقق إذا كان المشروع شغالاً بالفعل
    try:
        # ابحث عن زر Stop أو أي مؤشر أن المشروع شغال
        stop_button = page.locator("button:has-text('Stop')")
        if stop_button.count() > 0 and stop_button.is_visible(timeout=2000):
            log("✅ المشروع شغال بالفعل (زر Stop موجود).")
            return True
    except:
        pass
    
    log("⚠️ لم أجد زر Run - المشروع قد يكون شغالاً بالفعل أو الواجهة مختلفة.")
    return False


def main():
    cookies = load_cookies_for_playwright()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # شغّل مرئياً للتأكد
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_cookies(cookies)

        page = context.new_page()

        log(f"فتح المشروع: {PROJECT_URL}")
        page.goto(PROJECT_URL, wait_until="domcontentloaded", timeout=60000)

        # انتظر حتى تتحمّل الصفحة
        page.wait_for_timeout(5000)

        # تحقق من أننا مسجلون دخول
        if "/login" in page.url:
            log("⚠️ الكوكيز منتهية أو غير صحيحة - الصفحة رجّعتك لتسجيل الدخول.")
            log("📌 صدّر cookies.txt جديد من فايرفوكس وحاول تاني.")
            browser.close()
            sys.exit(1)

        log("✅ تم الدخول على المشروع بنجاح.")
        
        # حاول تشغيل المشروع
        log("🔍 جاري البحث عن زر Run...")
        ensure_project_running(page)

        log(f"🔄 هيتم تحديث الصفحة كل {REFRESH_INTERVAL_SECONDS} ثانية...")

        try:
            while True:
                time.sleep(REFRESH_INTERVAL_SECONDS)
                
                # إعادة تحميل الصفحة
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                
                # تحقق من الجلسة
                if "/login" in page.url:
                    log("❌ الجلسة انتهت أثناء التشغيل - محتاج كوكيز جديدة.")
                    break
                
                # تأكد أن المشروع شغال
                ensure_project_running(page)
                
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log(f"✅ تم التحديث - {now}")
                
        except KeyboardInterrupt:
            log("⏹️ تم الإيقاف يدويًا.")

        browser.close()


if __name__ == "__main__":
    main()
