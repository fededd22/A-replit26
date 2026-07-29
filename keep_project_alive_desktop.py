#!/usr/bin/env python3
"""
سكربت لكمبيوتر حقيقي (ويندوز/لينكس/ماك) - مش للموبايل.

بيستخدم Playwright عشان يفتح متصفح Chromium حقيقي، يحمّل الكوكيز بتاعتك
من cookies.txt، يدخل مباشرة على صفحة المشروع في ريبلت وهو مسجل دخول
تلقائيًا، يتحقق لو المشروع مطفي ويضغط زرار Run تلقائيًا عشان يشغّله،
وبعدين يعمل تحديث (reload) للصفحة كل 30 ثانية باستمرار (ويتأكد في كل
مرة إن المشروع لسه شغال، ولو اتطفى يضغط Run تاني).

بما إنه متصفح حقيقي بيشغّل JavaScript فعليًا، تحدي Cloudflare
("Just a moment...") هيتعدّى طبيعي زي أي متصفح عادي - وده الفرق
الجوهري عن محاولات bayدرويد اللي كانت بتستخدم requests بس.

المتطلبات (تتثبت مرة واحدة):
    pip install playwright
    playwright install chromium

الاستخدام:
    python keep_project_alive_desktop.py

للإيقاف: اضغط Ctrl+C في التيرمينال، أو اقفل نافذة المتصفح.
"""

import sys
import time
import http.cookiejar
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

COOKIE_FILE = "cookies.txt"
PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REFRESH_INTERVAL_SECONDS = 30


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def netscape_cookie_to_playwright(cookie) -> dict:
    """يحوّل كوكي من صيغة http.cookiejar لصيغة Playwright."""
    same_site_map = {True: "None", False: "Lax"}

    pw_cookie = {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path or "/",
        "secure": bool(cookie.secure),
        "httpOnly": bool(cookie._rest.get("HttpOnly", False))
        if hasattr(cookie, "_rest")
        else False,
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
    يحاول يلاقي زرار "Run" ويضغط عليه لو المشروع مطفي (مش شغال).
    لو المشروع شغال بالفعل، غالبًا الزرار بيبقى بشكل مختلف (Stop) أو
    مش موجود، فالدالة هتتجاهله من غير أي خطأ.
    """
    # أشكال محتملة لزرار Run في واجهة ريبلت (بيتغيّر أحيانًا حسب التحديثات)
    possible_selectors = [
        "button:has-text('Run')",
        "[aria-label='Run']",
        "button[data-cy='run-button']",
    ]

    for selector in possible_selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=3000):
                button.click()
                log("🟢 لقيت المشروع مطفي - دوست Run عشان يشتغل.")
                # ناخد وقت للمشروع عشان يبدأ فعليًا
                page.wait_for_timeout(5000)
                return True
        except Exception:
            continue

    return False


def main():
    cookies = load_cookies_for_playwright()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookies)

        page = context.new_page()

        log(f"فتح المشروع: {PROJECT_URL}")
        page.goto(PROJECT_URL, wait_until="networkidle")

        if "/login" in page.url:
            log(
                "⚠️ الكوكيز منتهية أو غير صحيحة - الصفحة رجّعتك لتسجيل الدخول.\n"
                "صدّر cookies.txt جديد من فايرفوكس وحاول تاني."
            )
        else:
            log("✅ تم الدخول على المشروع بنجاح.")
            ensure_project_running(page)

        log(f"هيتم تحديث الصفحة كل {REFRESH_INTERVAL_SECONDS} ثانية...")

        try:
            while True:
                time.sleep(REFRESH_INTERVAL_SECONDS)
                page.reload(wait_until="networkidle")
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if "/login" in page.url:
                    log("❌ الجلسة انتهت أثناء التشغيل - محتاج كوكيز جديدة.")
                    break
                ensure_project_running(page)
                log(f"✅ تم التحديث - {now}")
        except KeyboardInterrupt:
            log("تم الإيقاف يدويًا.")

        browser.close()


if __name__ == "__main__":
    main()
