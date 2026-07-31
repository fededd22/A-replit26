#!/usr/bin/env python3
"""
سكربت لتشغيل Google Cloud Shell تلقائياً وإعادة تشغيل نفسه كل 10 ثواني
"""

import sys
import time
import http.cookiejar
import re
import os
import subprocess
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ Playwright غير مثبت. قم بتشغيل:")
    print("   pip install playwright")
    print("   playwright install chromium")
    sys.exit(1)

COOKIE_FILE = "cookies_google.txt"  # ملف كوكيز خاص ب Google
PROJECT_URL = "https://shell.cloud.google.com/"
REFRESH_INTERVAL_SECONDS = 10
SCRIPT_NAME = "keep_google_shell_alive.py"


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
    if not os.path.exists(COOKIE_FILE):
        log(f"❌ ملف {COOKIE_FILE} مش موجود")
        log("📌 قم بتصدير كوكيز Google من Firefox أو Chrome")
        return []
    
    jar = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        log(f"❌ خطأ في تحميل الكوكيز: {e}")
        return []
    
    cookies = [netscape_cookie_to_playwright(c) for c in jar]
    log(f"تم تحميل {len(cookies)} كوكي")
    return cookies


def check_login_status(page):
    """التحقق من حالة تسجيل الدخول إلى Google"""
    try:
        # التحقق من وجود عناصر تشير إلى تسجيل الدخول
        user_elements = page.locator("[data-email], [aria-label*='Account'], .user-email").all()
        if user_elements:
            return True
        
        # التحقق من وجود زر تسجيل الدخول
        login_btn = page.locator("a:has-text('Sign in'), button:has-text('Sign in')").first
        if login_btn.count() > 0 and login_btn.is_visible(timeout=1000):
            return False
        
        # التحقق من وجود avatar/user icon
        avatar = page.locator("img[aria-label*='Account'], .avatar, .user-profile").first
        if avatar.count() > 0 and avatar.is_visible(timeout=1000):
            return True
            
        return True  # افترض أننا مسجلون
    except:
        return True


def activate_shell(page):
    """تشغيل Cloud Shell"""
    log("🔍 جاري البحث عن زر تفعيل Cloud Shell...")
    
    for attempt in range(8):
        page.wait_for_timeout(1500)
        
        # محددات زر تفعيل Cloud Shell
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
        
        # محاولة JavaScript
        try:
            result = page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button, [role="button"]');
                    for (let btn of buttons) {
                        const text = (btn.textContent || '').toLowerCase();
                        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const title = (btn.getAttribute('title') || '').toLowerCase();
                        const className = (btn.className || '').toLowerCase();
                        
                        if (text.includes('shell') || text.includes('terminal') || 
                            label.includes('shell') || label.includes('terminal') ||
                            title.includes('shell') || title.includes('terminal') ||
                            className.includes('shell') || className.includes('terminal')) {
                            btn.click();
                            return 'clicked';
                        }
                    }
                    return 'not_found';
                }
            """)
            if result == 'clicked':
                log("✅ تم تفعيل Cloud Shell عن طريق JavaScript")
                page.wait_for_timeout(5000)
                return True
        except:
            pass
        
        if attempt < 7:
            log(f"⚠️ محاولة {attempt + 1}/8...")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
    
    return False


def get_shell_status(page):
    """التحقق من حالة Cloud Shell"""
    try:
        # البحث عن مؤشرات أن Shell يعمل
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
        
        # البحث عن أزرار تشير إلى أن Shell يعمل
        stop_btn = page.locator("button:has-text('Stop Cloud Shell'), button:has-text('Close Cloud Shell'), button[aria-label*='close shell']").first
        if stop_btn.count() > 0 and stop_btn.is_visible(timeout=1000):
            return "running"
        
        return "stopped"
    except:
        return "unknown"


def run_once():
    """تشغيل دورة واحدة"""
    log("🚀 بدء دورة جديدة لـ Google Cloud Shell")
    
    cookies = load_cookies_for_playwright()
    if not cookies:
        log("❌ لا توجد كوكيز - قم بتصدير كوكيز Google")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (Chrome, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_cookies(cookies)
        page = context.new_page()

        log(f"📂 فتح: {PROJECT_URL}")
        page.goto(PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # التحقق من تسجيل الدخول
        if not check_login_status(page):
            log("❌ غير مسجل دخول - قم بتحديث الكوكيز")
            browser.close()
            return False

        log("✅ تم تسجيل الدخول")

        # التحقق من حالة Shell
        status = get_shell_status(page)
        log(f"📊 حالة Cloud Shell: {status}")

        # تفعيل Shell إذا كان متوقفاً
        if status == "stopped":
            if activate_shell(page):
                log("✅ تم تفعيل Cloud Shell")
            else:
                log("⚠️ فشل في تفعيل Cloud Shell")
        else:
            log("✅ Cloud Shell يعمل بالفعل")

        # البحث عن رابط Shell (اختياري)
        shell_url = None
        try:
            # البحث عن iframe الخاص بـ Cloud Shell
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
        f.write(f"آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"الحالة: {status}\n")
        if shell_url:
            f.write(f"رابط Shell: {shell_url}\n")

    return True


def main():
    """الحلقة الرئيسية"""
    log("🔥 بدء التشغيل لإبقاء Google Cloud Shell نشطاً")
    log(f"⏱️ سيعاد التشغيل كل {REFRESH_INTERVAL_SECONDS} ثانية")
    
    while True:
        try:
            run_once()
            
            log(f"⏳ الانتظار {REFRESH_INTERVAL_SECONDS} ثواني...")
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
    main()