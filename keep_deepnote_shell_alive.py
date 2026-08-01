#!/usr/bin/env python3
"""
سكربت لتشغيل Deepnote Cloud Shell تلقائياً وإعادة تشغيل نفسه كل 10 ثواني
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

COOKIE_FILE = "deepnote.com_cookies.txt"  # ملف كوكيز خاص بـ Deepnote
PROJECT_URL = "https://deepnote.com/workspace/molitiiy-19213b31-958f-4741-bf2b-e1ad5a5efec0/project/Molista-docks-Untitled-project-88c8ee41-f97b-44f8-89d3-917380dc5352/notebook/394586d8c0aa4869ac13f10520d29e83?secondary-sidebar-autoopen=true&secondary-sidebar=agent#terminal:0cef2032-e785-45b1-94c7-2b1bfb004032"
REFRESH_INTERVAL_SECONDS = 10
SCRIPT_NAME = "keep_deepnote_shell_alive.py"


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
        log("📌 قم بتصدير كوكيز Deepnote من Firefox أو Chrome")
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
    """التحقق من حالة تسجيل الدخول إلى Deepnote"""
    try:
        # التحقق من وجود عناصر تشير إلى تسجيل الدخول
        user_elements = page.locator("[data-email], [aria-label*='Account'], .user-email, .avatar").all()
        if user_elements:
            return True
        
        # التحقق من وجود زر تسجيل الدخول
        login_btn = page.locator("a:has-text('Sign in'), button:has-text('Sign in'), a:has-text('Login'), button:has-text('Login')").first
        if login_btn.count() > 0 and login_btn.is_visible(timeout=1000):
            return False
        
        # التحقق من وجود صورة المستخدم
        avatar = page.locator("img[aria-label*='Account'], .avatar, .user-profile, img[alt*='user']").first
        if avatar.count() > 0 and avatar.is_visible(timeout=1000):
            return True
            
        return True  # افترض أننا مسجلون
    except:
        return True


def activate_shell(page):
    """تشغيل Cloud Shell في Deepnote"""
    log("🔍 جاري البحث عن زر تفعيل Terminal...")
    
    for attempt in range(8):
        page.wait_for_timeout(1500)
        
        # محددات زر تفعيل Terminal في Deepnote
        selectors = [
            "button:has-text('Terminal')",
            "button:has-text('terminal')",
            "button:has-text('Open Terminal')",
            "button:has-text('Start Terminal')",
            "button[aria-label*='Terminal']",
            "button:has-text('activate')",
            "button:has-text('shell')",
            "button:has(svg[viewBox*='terminal'])",
            "button:has(svg[viewBox*='shell'])",
            "button[class*='terminal']",
            "button[class*='shell']",
            "button[data-testid*='terminal']",
            "button[data-testid*='shell']",
            "button[aria-label*='terminal']",
            "button[aria-label*='shell']",
            "button:has-text('>_')",
            "button:has-text('$_')",
            "button:has-text('console')",
            "button:has-text('▶')",
            "button:has-text('▼')",
            "[role='button']:has-text('Terminal')",
        ]
        
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    log(f"✅ تم العثور على زر Terminal: {selector}")
                    btn.click()
                    log("🟢 تم تفعيل Terminal")
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
                        
                        if (text.includes('terminal') || text.includes('shell') || 
                            label.includes('terminal') || label.includes('shell') ||
                            title.includes('terminal') || title.includes('shell') ||
                            className.includes('terminal') || className.includes('shell')) {
                            btn.click();
                            return 'clicked';
                        }
                    }
                    return 'not_found';
                }
            """)
            if result == 'clicked':
                log("✅ تم تفعيل Terminal عن طريق JavaScript")
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
    """التحقق من حالة Terminal في Deepnote"""
    try:
        # البحث عن مؤشرات أن Terminal يعمل
        indicators = [
            "iframe[src*='terminal']",
            "iframe[title*='Terminal']",
            "div[class*='terminal']",
            "div[class*='console']",
            "div[aria-label*='Terminal']",
            "div[aria-label*='terminal']",
            ".xterm",
            ".terminal",
        ]
        
        for selector in indicators:
            try:
                el = page.locator(selector).first
                if el.count() > 0 and el.is_visible(timeout=1000):
                    return "running"
            except:
                continue
        
        # البحث عن أزرار تشير إلى أن Terminal يعمل
        stop_btn = page.locator("button:has-text('Stop Terminal'), button:has-text('Close Terminal'), button[aria-label*='close terminal']").first
        if stop_btn.count() > 0 and stop_btn.is_visible(timeout=1000):
            return "running"
        
        return "stopped"
    except:
        return "unknown"


def run_once():
    """تشغيل دورة واحدة"""
    log("🚀 بدء دورة جديدة لـ Deepnote Terminal")
    
    cookies = load_cookies_for_playwright()
    if not cookies:
        log("❌ لا توجد كوكيز - قم بتصدير كوكيز Deepnote")
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

        # التحقق من حالة Terminal
        status = get_shell_status(page)
        log(f"📊 حالة Terminal: {status}")

        # تفعيل Terminal إذا كان متوقفاً
        if status == "stopped":
            if activate_shell(page):
                log("✅ تم تفعيل Terminal")
            else:
                log("⚠️ فشل في تفعيل Terminal")
        else:
            log("✅ Terminal يعمل بالفعل")

        browser.close()

    # حفظ المعلومات
    with open("deepnote_shell_status.txt", "w") as f:
        f.write(f"آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"الحالة: {status}\n")

    return True


def main():
    """الحلقة الرئيسية"""
    log("🔥 بدء التشغيل لإبقاء Deepnote Terminal نشطاً")
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
