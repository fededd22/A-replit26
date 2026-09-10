#!/usr/bin/env python3
"""
سكربت مدمج محسّن - Replit + Google Cloud Shell مع Keep Alive
تسجيل دخول تلقائي متعدد المراحل (Cookies → Email/Password → OAuth)
"""

import sys
import time
import http.cookiejar
import re
import os
import json
import signal
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ==================== الإعدادات ====================
REPLIT_COOKIE_FILE = "cookies.txt"
REPLIT_PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REPLIT_LOGIN_URL = "https://replit.com/login"
REPLIT_REFRESH_INTERVAL = 30
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev(?::\d+)?"

GOOGLE_COOKIE_FILE = "cookies_google.txt"
GOOGLE_PROJECT_URL = "https://shell.cloud.google.com/"
GOOGLE_REFRESH_INTERVAL = 20

KEEP_ALIVE_PORT = 8080

# بيانات الدخول
REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"

# متغيرات عامة
last_webview_url = None
last_update_time = None
last_google_status = None
last_google_update = None
last_login_attempt = 0
LOGIN_COOLDOWN = 60  # ثانية بين محاولات تسجيل الدخول
running = True


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ==================== إدارة الكوكيز ====================

def clean_cookie(cookie) -> dict:
    """تنظيف الكوكي لصيغة Playwright الصحيحة"""
    if not isinstance(cookie, dict):
        return None
    
    allowed = ['name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite']
    cleaned = {}
    
    for field in allowed:
        if field in cookie and cookie[field] is not None:
            if field == 'expires':
                if isinstance(cookie[field], (int, float)):
                    cleaned[field] = int(cookie[field])
                elif isinstance(cookie[field], str):
                    try:
                        dt = datetime.fromisoformat(cookie[field].replace('Z', '+00:00'))
                        cleaned[field] = int(dt.timestamp())
                    except:
                        continue
            elif field in ('httpOnly', 'secure'):
                cleaned[field] = bool(cookie[field])
            elif field == 'sameSite':
                if cookie[field] in ('Strict', 'Lax', 'None'):
                    cleaned[field] = cookie[field]
            else:
                cleaned[field] = str(cookie[field])
    
    if 'name' not in cleaned or 'value' not in cleaned:
        return None
    if 'domain' not in cleaned:
        return None
    
    cleaned['domain'] = cleaned['domain'].lstrip('.')
    cleaned['path'] = cleaned.get('path', '/')
    return cleaned


def load_cookies_any_format(cookie_file):
    """تحميل الكوكيز من أي صيغة (Netscape أو JSON)"""
    if not os.path.exists(cookie_file):
        return []
    
    # محاولة JSON أولاً
    try:
        with open(cookie_file, 'r') as f:
            content = f.read().strip()
        
        if content.startswith('[') or content.startswith('{'):
            data = json.loads(content)
            if isinstance(data, dict) and 'cookies' in data:
                data = data['cookies']
            
            cleaned = []
            for c in data:
                cc = clean_cookie(c)
                if cc:
                    cleaned.append(cc)
            
            if cleaned:
                log(f"✅ تم تحميل {len(cleaned)} كوكي (JSON) من {cookie_file}")
                return cleaned
    except Exception as e:
        pass
    
    # محاولة Netscape
    try:
        jar = http.cookiejar.MozillaCookieJar(cookie_file)
        jar.load(ignore_discard=True, ignore_expires=True)
        
        cleaned = []
        for c in jar:
            cc = clean_cookie({
                'name': c.name,
                'value': c.value,
                'domain': c.domain,
                'path': c.path or '/',
                'secure': bool(c.secure),
                'httpOnly': bool(c._rest.get('HttpOnly', False)) if hasattr(c, '_rest') else False,
                'expires': c.expires,
            })
            if cc:
                cleaned.append(cc)
        
        if cleaned:
            log(f"✅ تم تحميل {len(cleaned)} كوكي (Netscape) من {cookie_file}")
            return cleaned
    except Exception as e:
        log(f"⚠️ فشل تحميل Netscape: {e}")
    
    return []


def save_cookies(cookies, cookie_file):
    """حفظ الكوكيز بصيغة JSON و Netscape معاً"""
    try:
        with open(cookie_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        log(f"💾 تم حفظ {len(cookies)} كوكي في {cookie_file}")
    except Exception as e:
        log(f"⚠️ خطأ في حفظ الكوكيز: {e}")


# ==================== تسجيل الدخول إلى Replit ====================

def human_type(page, selector_list, text, field_name="حقل"):
    """كتابة نص في حقل مع محاولة عدة selectors"""
    for selector in selector_list:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible(timeout=2000):
                el.click()
                page.wait_for_timeout(200)
                el.fill("")
                page.wait_for_timeout(100)
                el.type(text, delay=50)
                log(f"✅ تم إدخال {field_name} عبر {selector}")
                return True
        except Exception:
            continue
    
    # محاولة JavaScript كخطة بديلة
    try:
        result = page.evaluate(f"""
            (text) => {{
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {{
                    const type = (inp.type || '').toLowerCase();
                    const name = (inp.name || '').toLowerCase();
                    const placeholder = (inp.placeholder || '').toLowerCase();
                    const ariaLabel = (inp.getAttribute('aria-label') || '').toLowerCase();
                    
                    if ({selector_list!r}.some(s => {{
                        const kw = s.toLowerCase();
                        return type.includes(kw) || name.includes(kw) || 
                               placeholder.includes(kw) || ariaLabel.includes(kw);
                    }})) {{
                        inp.focus();
                        inp.value = text;
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
            }}
        """, text)
        if result:
            log(f"✅ تم إدخال {field_name} عبر JavaScript")
            return True
    except Exception as e:
        log(f"⚠️ فشل JavaScript: {e}")
    
    return False


def click_first_available(page, selectors, description="زر"):
    """النقر على أول عنصر متاح من قائمة selectors"""
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0 and el.is_visible(timeout=1500):
                el.click(timeout=3000)
                log(f"✅ تم النقر على {description}: {selector}")
                return True
        except Exception:
            continue
    return False


def login_to_replit() -> bool:
    """تسجيل دخول كامل إلى Replit مع دعم OAuth"""
    global last_login_attempt
    
    now = time.time()
    if now - last_login_attempt < LOGIN_COOLDOWN:
        wait = int(LOGIN_COOLDOWN - (now - last_login_attempt))
        log(f"⏸️ في فترة الانتظار ({wait}s) قبل محاولة دخول جديدة")
        return False
    
    last_login_attempt = now
    log("🔑 بدء عملية تسجيل الدخول إلى Replit...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-gpu',
                ]
            )
            
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
            )
            
            # إخفاء علامات الأتمتة
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)
            
            page = context.new_page()
            
            # ===== 1. فتح صفحة تسجيل الدخول =====
            log("🌐 فتح صفحة تسجيل الدخول...")
            try:
                page.goto(REPLIT_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت مهلة تحميل صفحة الدخول")
                browser.close()
                return False
            
            page.wait_for_timeout(4000)
            log(f"📍 URL الحالي: {page.url}")
            
            # ===== 2. محاولة الدخول عبر Google إذا ظهر زر =====
            google_selectors = [
                "button:has-text('Google')",
                "a:has-text('Google')",
                "button:has-text('Continue with Google')",
                "[data-provider='google']",
                "button[aria-label*='Google']",
            ]
            
            if click_first_available(page, google_selectors, "زر Google"):
                log("🔵 تم اختيار تسجيل الدخول عبر Google")
                page.wait_for_timeout(5000)
                
                # اختيار الحساب من صفحة Google
                try:
                    # انتظار ظهور قائمة الحسابات
                    page.wait_for_selector("[data-identifier], [data-email]", timeout=15000)
                    
                    # محاولة النقر على الحساب المطابق
                    account_selectors = [
                        f"div[data-identifier='{REPLIT_EMAIL}']",
                        f"[data-email='{REPLIT_EMAIL}']",
                        f"li:has-text('{REPLIT_EMAIL}')",
                        "div[role='link']:has-text('@gmail.com')",
                    ]
                    
                    if not click_first_available(page, account_selectors, "حساب Google"):
                        # النقر على أول حساب متاح
                        click_first_available(page, [
                            "div[data-identifier]",
                            "li div[role='link']",
                        ], "أول حساب Google متاح")
                    
                    page.wait_for_timeout(8000)
                    log(f"📍 بعد اختيار الحساب: {page.url}")
                except Exception as e:
                    log(f"⚠️ خطأ في OAuth: {e}")
            
            # ===== 3. إذا لم ننجح، ملء النموذج =====
            if "login" in page.url.lower() or "signin" in page.url.lower():
                log("📝 ملء نموذج البريد/كلمة المرور...")
                
                # حقل البريد
                email_filled = human_type(page, [
                    "input[type='email']",
                    "input[name='email']",
                    "input[name='username']",
                    "input[placeholder*='email' i]",
                    "input[placeholder*='username' i]",
                    "input[autocomplete='email']",
                    "input[autocomplete='username']",
                    "input[id*='email' i]",
                ], REPLIT_EMAIL, "البريد الإلكتروني")
                
                page.wait_for_timeout(1500)
                
                # زر Continue بعد البريد (بعض النماذج مرحلية)
                if email_filled:
                    click_first_available(page, [
                        "button:has-text('Continue')",
                        "button:has-text('Next')",
                        "button[type='submit']",
                    ], "زر Continue")
                    page.wait_for_timeout(2500)
                
                # حقل كلمة المرور
                password_filled = human_type(page, [
                    "input[type='password']",
                    "input[name='password']",
                    "input[autocomplete='current-password']",
                    "input[id*='password' i]",
                ], REPLIT_PASSWORD, "كلمة المرور")
                
                page.wait_for_timeout(1500)
                
                # زر الإرسال
                if password_filled:
                    click_first_available(page, [
                        "button[type='submit']:has-text('Log in')",
                        "button[type='submit']:has-text('Sign in')",
                        "button:has-text('Log in')",
                        "button:has-text('Sign in')",
                        "button[type='submit']",
                    ], "زر تسجيل الدخول")
                    
                    page.wait_for_timeout(8000)
            
            # ===== 4. التحقق من نجاح الدخول =====
            current_url = page.url
            log(f"📍 URL بعد المحاولة: {current_url}")
            
            # علامات الفشل
            if any(x in current_url.lower() for x in ['/login', '/signin']):
                # ربما هناك تحقق إضافي
                try:
                    error_text = page.text_content("body") or ""
                    if "incorrect" in error_text.lower() or "invalid" in error_text.lower():
                        log("❌ بيانات دخول خاطئة")
                    else:
                        log("⚠️ ما زلنا في صفحة الدخول")
                except:
                    pass
                
                # محاولة أخيرة: التحقق من replit.com/home
                try:
                    page.goto("https://replit.com/home", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                    current_url = page.url
                except:
                    pass
            
            if "login" in current_url.lower() or "signin" in current_url.lower():
                log("❌ فشل تسجيل الدخول")
                browser.close()
                return False
            
            log("✅ تم تسجيل الدخول بنجاح!")
            
            # ===== 5. حفظ الكوكيز =====
            cookies_raw = context.cookies()
            cookies = [clean_cookie(c) for c in cookies_raw]
            cookies = [c for c in cookies if c]
            
            browser.close()
            
            if cookies:
                save_cookies(cookies, REPLIT_COOKIE_FILE)
                return True
            else:
                log("❌ لم يتم الحصول على كوكيز")
                return False
    
    except Exception as e:
        log(f"❌ خطأ في تسجيل الدخول: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== منطق Replit ====================

def press_run_button(page, max_attempts=8) -> bool:
    """البحث عن زر Run والضغط عليه"""
    log("🔍 البحث عن زر Run...")
    
    run_selectors = [
        "button:has-text('Run')",
        "button[aria-label='Run']",
        "button[aria-label*='Run' i]",
        "[data-testid='run-button']",
        "button:has(svg[viewBox*='play'])",
        "button:has(span:has-text('Run'))",
    ]
    
    for attempt in range(max_attempts):
        page.wait_for_timeout(1500)
        
        # التحقق من وجود Stop أولاً
        try:
            stop = page.locator("button:has-text('Stop')").first
            if stop.count() > 0 and stop.is_visible(timeout=1000):
                log("✅ المشروع يعمل بالفعل")
                return True
        except:
            pass
        
        if click_first_available(page, run_selectors, "زر Run"):
            page.wait_for_timeout(5000)
            return True
        
        # محاولة JavaScript
        try:
            result = page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        const t = (b.textContent || '').trim().toLowerCase();
                        const l = (b.getAttribute('aria-label') || '').toLowerCase();
                        if ((t === 'run' || l === 'run') && b.offsetParent !== null) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if result:
                log("✅ تم النقر على Run عبر JavaScript")
                page.wait_for_timeout(5000)
                return True
        except:
            pass
        
        if attempt < max_attempts - 1:
            log(f"⚠️ محاولة {attempt+1}/{max_attempts}، إعادة تحميل...")
            try:
                page.reload(wait_until="domcontentloaded")
            except:
                pass
    
    return False


def get_webview_url(page) -> str:
    """استخراج رابط Webview"""
    log("🔍 البحث عن رابط Webview...")
    
    for _ in range(5):
        # from iframes
        try:
            for iframe in page.locator("iframe").all():
                src = iframe.get_attribute("src") or ""
                m = re.search(WEBVIEW_PATTERN, src)
                if m:
                    return m.group(0)
        except:
            pass
        
        # from page text
        try:
            body = page.text_content("body") or ""
            matches = re.findall(WEBVIEW_PATTERN, body)
            if matches:
                return matches[0]
        except:
            pass
        
        # from JS
        try:
            result = page.evaluate(r"""
                () => {
                    const re = /https?:\/\/[a-f0-9\-]+\.replit\.dev(?::\d+)?/;
                    const text = document.body.innerText || '';
                    let m = text.match(re);
                    if (m) return m[0];
                    for (const f of document.querySelectorAll('iframe')) {
                        m = (f.src || '').match(re);
                        if (m) return m[0];
                    }
                    return null;
                }
            """)
            if result:
                return result
        except:
            pass
        
        page.wait_for_timeout(2000)
    
    return None


def run_replit_once() -> bool:
    """دورة واحدة لـ Replit"""
    global last_webview_url, last_update_time
    
    log("=" * 50)
    log("🔄 دورة Replit")
    
    cookies = load_cookies_any_format(REPLIT_COOKIE_FILE)
    webview_url = None
    need_login = False
    
    # إذا لم توجد كوكيز، سجّل دخول
    if not cookies:
        log("📂 لا توجد كوكيز - محاولة تسجيل الدخول...")
        if not login_to_replit():
            return False
        cookies = load_cookies_any_format(REPLIT_COOKIE_FILE)
        if not cookies:
            return False
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox',
                      '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            
            # إضافة الكوكيز مع تجاهل الأخطاء
            added = 0
            for c in cookies:
                try:
                    context.add_cookies([c])
                    added += 1
                except Exception:
                    continue
            log(f"🍪 تمت إضافة {added}/{len(cookies)} كوكي")
            
            page = context.new_page()
            
            try:
                page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
            except PWTimeout:
                log("⚠️ انتهت مهلة التحميل")
                browser.close()
                return False
            
            # التحقق من انتهاء الكوكيز
            if "/login" in page.url or "/signin" in page.url:
                log("❌ الكوكيز منتهية - إعادة تسجيل الدخول...")
                need_login = True
            else:
                log("✅ تم فتح المشروع")
                
                # الضغط على Run
                press_run_button(page, max_attempts=6)
                
                # استخراج الرابط
                webview_url = get_webview_url(page)
            
            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return False
    
    # إذا احتجنا تسجيل دخول، افعل ذلك وأعد المحاولة
    if need_login:
        try:
            os.remove(REPLIT_COOKIE_FILE)
        except:
            pass
        if login_to_replit():
            return run_replit_once()
        return False
    
    if webview_url:
        last_webview_url = webview_url
        last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log(f"🌐 Webview: {webview_url}")
        with open("webview_url.txt", "w") as f:
            f.write(f"{webview_url}\n{last_update_time}\n")
        return True
    else:
        log("⚠️ لم يتم العثور على رابط Webview")
        return False


# ==================== Google Cloud Shell ====================

def get_shell_status(page) -> str:
    try:
        for sel in [
            "iframe[src*='cloud-shell']",
            "iframe[title*='Cloud Shell']",
            "div[class*='terminal']",
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=1000):
                    return "running"
            except:
                continue
        return "stopped"
    except:
        return "unknown"


def activate_shell(page) -> bool:
    log("🔍 البحث عن زر تفعيل Cloud Shell...")
    
    selectors = [
        "button:has-text('Activate Cloud Shell')",
        "button:has-text('Open Cloud Shell')",
        "button:has-text('Start Cloud Shell')",
        "button[aria-label*='Cloud Shell']",
        "button:has-text('activate')",
        "button:has(svg[viewBox*='terminal'])",
    ]
    
    for attempt in range(5):
        if click_first_available(page, selectors, "زر Cloud Shell"):
            page.wait_for_timeout(5000)
            return True
        page.wait_for_timeout(2000)
    
    return False


def run_google_once() -> bool:
    global last_google_status, last_google_update
    
    log("🔄 دورة Google Cloud Shell")
    
    cookies = load_cookies_any_format(GOOGLE_COOKIE_FILE)
    if not cookies:
        log("❌ لا توجد كوكيز Google")
        last_google_status = "no_cookies"
        last_google_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return False
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox',
                      '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            
            for c in cookies:
                try:
                    context.add_cookies([c])
                except:
                    continue
            
            page = context.new_page()
            page.goto(GOOGLE_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            
            status = get_shell_status(page)
            log(f"📊 حالة Shell: {status}")
            last_google_status = status
            
            if status == "stopped":
                if activate_shell(page):
                    last_google_status = "activated"
            
            last_google_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open("google_shell_status.txt", "w") as f:
                f.write(f"آخر تحديث: {last_google_update}\nالحالة: {last_google_status}\n")
            
            browser.close()
            return True
    except Exception as e:
        log(f"❌ خطأ Google: {e}")
        last_google_status = "error"
        last_google_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return False


# ==================== Keep Alive Server ====================

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
            <meta http-equiv="refresh" content="30"><title>Keep Alive</title>
            <style>body{{font-family:Arial;text-align:center;padding:50px;
            background:#0a0a0a;color:#00ff88}}h1{{font-size:2.5em}}
            .box{{background:#1a1a2e;padding:20px;border-radius:10px;margin:20px 0;
            border:1px solid #333}}.box-title{{color:#00ccff}}
            .time{{color:#888;font-size:0.85em}}</style></head><body>
            <h1>🚀 Keep Alive Active</h1>
            <div class="time">تم التحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            <div class="box"><div class="box-title">🔄 Replit</div>
            <div>{last_webview_url or '⏳ جاري البحث...'}</div>
            <div class="time">آخر تحديث: {last_update_time or '—'}</div></div>
            <div class="box"><div class="box-title">☁️ Google</div>
            <div>الحالة: {last_google_status or '⏳'}</div>
            <div class="time">آخر تحديث: {last_google_update or '—'}</div></div>
            </body></html>"""
            self.wfile.write(html.encode('utf-8'))
        elif parsed.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "replit": {"webview_url": last_webview_url, "last_update": last_update_time},
                "google": {"status": last_google_status, "last_update": last_google_update},
            }).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *args):
        pass


def run_keep_alive_server():
    try:
        server = HTTPServer(('0.0.0.0', KEEP_ALIVE_PORT), KeepAliveHandler)
        log(f"🔌 خادم Keep Alive على المنفذ {KEEP_ALIVE_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"⚠️ خطأ Keep Alive: {e}")


# ==================== Main ====================

def main():
    global running
    
    log("🔥 بدء السكربت المدمج")
    log(f"📁 Replit cookies: {REPLIT_COOKIE_FILE}")
    log(f"📁 Google cookies: {GOOGLE_COOKIE_FILE}")
    
    # فحص أولي: هل توجد كوكيز؟
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log("🔑 لا توجد كوكيز Replit - تسجيل دخول أولي...")
        if login_to_replit():
            log("✅ تم تسجيل الدخول بنجاح وحفظ الكوكيز")
        else:
            log("⚠️ فشل تسجيل الدخول الأولي - سيُعاد المحاولة لاحقاً")
    
    threading.Thread(target=run_keep_alive_server, daemon=True).start()
    
    google_counter = 0
    replit_counter = 0
    
    while running:
        try:
            # Google كل دورة (20 ثانية)
            if google_counter % 2 == 0:
                run_google_once()
            
            # Replit كل 3 دورات (~30 ثانية)
            if replit_counter % 3 == 0:
                run_replit_once()
            
            google_counter += 1
            replit_counter += 1
            
            log("⏳ الانتظار 10 ثواني...")
            for i in range(10, 0, -1):
                if not running:
                    break
                if i <= 3 or i == 5:
                    log(f"⏳ {i}s")
                time.sleep(1)
        
        except KeyboardInterrupt:
            log("⏹️ إيقاف")
            running = False
            break
        except Exception as e:
            log(f"❌ خطأ عام: {e}")
            time.sleep(5)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    main()
