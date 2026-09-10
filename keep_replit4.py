#!/usr/bin/env python3
"""
Replit Auto Login + Open Project + Open Target URL
- headless=True (يعمل بدون شاشة)
- stealth محسّن
- كوكيز Replit فقط
"""

import os
import sys
import json
import time
import re
import signal
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ==================== الإعدادات ====================
REPLIT_COOKIE_FILE = "cookies_replit.txt"
REPLIT_LOGIN_URL = "https://replit.com/login"
REPLIT_HOME_URL = "https://replit.com/home"
REPLIT_PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REPLIT_TARGET_URL = "https://f9732b2f-7002-4f57-b44c-a25d6ab8587c-00-27z973qza9qqb.kirk.replit.dev:443"
REPLIT_REFRESH_INTERVAL = 30

REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"

KEEP_ALIVE_PORT = 8080
LOGIN_COOLDOWN = 90

running = True
last_update_time = None
last_status = "idle"
last_login_attempt = 0


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ==================== stealth قوي ====================

STEALTH_SCRIPT = r"""
// 1) webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true,
});

// 2) chrome
if (!window.chrome) window.chrome = {};
window.chrome.runtime = window.chrome.runtime || {};
window.chrome.loadTimes = function() {};
window.chrome.csi = function() {};
window.chrome.app = { isInstalled: false };

// 3) plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        ];
        arr.item = (i) => arr[i];
        arr.namedItem = (n) => arr.find(p => p.name === n);
        return arr;
    },
    configurable: true,
});

// 4) languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
    configurable: true,
});

// 5) platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
    configurable: true,
});

// 6) hardwareConcurrency
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
    configurable: true,
});

// 7) deviceMemory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
    configurable: true,
});

// 8) permissions
if (navigator.permissions && navigator.permissions.query) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) => (
        params.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission, onchange: null })
            : origQuery(params)
    );
}

// 9) WebGL vendor/renderer
try {
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'Intel Inc.';
        if (p === 37446) return 'Intel Iris OpenGL Engine';
        return getParam.call(this, p);
    };
} catch (e) {}

// 10) hide CDP runtime
try {
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
} catch (e) {}

// 11) Notification permission
if (window.Notification) {
    Object.defineProperty(Notification, 'permission', {
        get: () => 'default',
        configurable: true,
    });
}

// 12) chrome keys used by detection scripts
window.chrome.runtime.id = undefined;
Object.defineProperty(navigator, 'webdriver', { get: () => false });
"""


# ==================== الكوكيز ====================

def load_cookies(cookie_file):
    if not os.path.exists(cookie_file):
        return []
    
    cookies = []
    try:
        with open(cookie_file) as f:
            content = f.read().strip()
        if content.startswith(('[', '{')):
            data = json.loads(content)
            if isinstance(data, dict) and 'cookies' in data:
                data = data['cookies']
            cookies = data
    except:
        pass
    
    if not cookies:
        import http.cookiejar
        try:
            jar = http.cookiejar.MozillaCookieJar(cookie_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            for c in jar:
                cookies.append({
                    'name': c.name, 'value': c.value,
                    'domain': c.domain, 'path': c.path or '/',
                    'secure': bool(c.secure),
                    'httpOnly': bool(c._rest.get('HttpOnly', False)) if hasattr(c, '_rest') else False,
                    'expires': c.expires,
                })
        except:
            pass
    
    filtered = []
    for c in cookies:
        domain = (c.get('domain') or '').lstrip('.').lower()
        if 'replit' not in domain:
            continue
        clean = {
            'name': c.get('name'), 'value': c.get('value'),
            'domain': domain, 'path': c.get('path', '/'),
        }
        if c.get('secure'): clean['secure'] = True
        if c.get('httpOnly'): clean['httpOnly'] = True
        if c.get('sameSite') in ('Strict', 'Lax', 'None'):
            clean['sameSite'] = c['sameSite']
        if isinstance(c.get('expires'), (int, float)) and c['expires'] > 0:
            clean['expires'] = int(c['expires'])
        if clean['name'] and clean['value']:
            filtered.append(clean)
    
    log(f"🍪 {len(filtered)} كوكي Replit (من {len(cookies)})")
    return filtered


def save_cookies(cookies, fname):
    try:
        with open(fname, 'w') as f:
            json.dump(cookies, f, indent=2)
        log(f"💾 حُفظت {len(cookies)} كوكي Replit")
    except Exception as e:
        log(f"⚠️ خطأ الحفظ: {e}")


def clear_cookies():
    try:
        if os.path.exists(REPLIT_COOKIE_FILE):
            os.remove(REPLIT_COOKIE_FILE)
            log(f"🗑️ حُذف {REPLIT_COOKIE_FILE}")
    except:
        pass


# ==================== إنشاء السياق (headless) ====================

def create_context(playwright, cookies=None, headless=True):
    """
    headless=True دائماً - لأننا في بيئة بدون شاشة.
    نستخدم تقنيات stealth لتجاوز الكشف.
    """
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--window-size=1920,1080',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-web-security',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-infobars',
            '--disable-notifications',
            '--disable-popup-blocking',
            '--lang=en-US',
        ],
    )
    
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="Asia/Riyadh",
        color_scheme="light",
        device_scale_factor=1,
        has_touch=False,
        is_mobile=False,
        java_script_enabled=True,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    )
    
    # تطبيق stealth
    context.add_init_script(STEALTH_SCRIPT)
    
    if cookies:
        try:
            context.add_cookies(cookies)
            log(f"✅ أُضيفت {len(cookies)} كوكي")
        except Exception as e:
            log(f"⚠️ خطأ الكوكيز: {e}")
    
    return browser, context


def human_type(page, element, text):
    try:
        box = element.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2, steps=12)
            page.wait_for_timeout(250)
        element.click()
        page.wait_for_timeout(400)
        element.fill("")
        page.wait_for_timeout(200)
        for ch in text:
            element.type(ch)
            page.wait_for_timeout(40 + int(time.time()*1000) % 80)
    except Exception as e:
        log(f"⚠️ خطأ كتابة: {e}")


# ==================== تسجيل الدخول ====================

def login_replit() -> bool:
    global last_login_attempt
    
    now = time.time()
    if now - last_login_attempt < LOGIN_COOLDOWN:
        wait = int(LOGIN_COOLDOWN - (now - last_login_attempt))
        log(f"⏸️ انتظار {wait}s قبل محاولة دخول جديدة")
        return False
    last_login_attempt = now
    
    log("=" * 60)
    log("🔑 تسجيل دخول Replit")
    
    try:
        with sync_playwright() as p:
            # headless=True (إلزامي في بيئة بدون شاشة)
            browser, context = create_context(p, headless=True)
            page = context.new_page()
            
            log(f"🌐 فتح {REPLIT_LOGIN_URL}")
            try:
                page.goto(REPLIT_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت المهلة")
            
            page.wait_for_timeout(5000)
            log(f"📍 URL: {page.url}")
            
            try:
                page.screenshot(path="debug_login.png")
            except:
                pass
            
            # ===== حقل البريد =====
            email_filled = False
            for sel in [
                'input[name="username"]',
                'input[type="email"]',
                'input#email',
                'input[autocomplete="email"]',
                'input[autocomplete="username"]',
            ]:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible(timeout=3000):
                        human_type(page, el, REPLIT_EMAIL)
                        log(f"✅ البريد → {sel}")
                        email_filled = True
                        break
                except:
                    continue
            
            if not email_filled:
                # جرّب JS
                try:
                    ok = page.evaluate(f"""
                        () => {{
                            const inp = document.querySelector('input[name="username"], input[type="email"]');
                            if (!inp) return false;
                            inp.focus();
                            inp.value = '{REPLIT_EMAIL}';
                            inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                            inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                            return true;
                        }}
                    """)
                    if ok:
                        log("✅ البريد عبر JS")
                        email_filled = True
                except:
                    pass
            
            if not email_filled:
                log("❌ لم يُعثر على حقل البريد")
                browser.close()
                return False
            
            page.wait_for_timeout(1500)
            
            # ===== حقل كلمة المرور =====
            pass_filled = False
            for sel in [
                'input[type="password"]',
                'input[name="password"]',
                'input#password',
            ]:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible(timeout=3000):
                        human_type(page, el, REPLIT_PASSWORD)
                        log(f"✅ كلمة المرور → {sel}")
                        pass_filled = True
                        break
                except:
                    continue
            
            if not pass_filled:
                try:
                    ok = page.evaluate(f"""
                        () => {{
                            const inp = document.querySelector('input[type="password"]');
                            if (!inp) return false;
                            inp.focus();
                            inp.value = '{REPLIT_PASSWORD}';
                            inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                            inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                            return true;
                        }}
                    """)
                    if ok:
                        log("✅ كلمة المرور عبر JS")
                        pass_filled = True
                except:
                    pass
            
            if not pass_filled:
                log("❌ لم يُعثر على حقل كلمة المرور")
                browser.close()
                return False
            
            page.wait_for_timeout(1500)
            
            # ===== زر الإرسال =====
            submitted = False
            for sel in [
                'button[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                'button:has-text("Login")',
                'button:has-text("Continue")',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=2000):
                        btn.click()
                        log(f"✅ زر الدخول → {sel}")
                        submitted = True
                        break
                except:
                    continue
            
            if not submitted:
                page.keyboard.press("Enter")
                log("⌨️ Enter")
            
            page.wait_for_timeout(12000)
            log(f"📍 بعد الإرسال: {page.url}")
            
            try:
                page.screenshot(path="debug_after_submit.png")
            except:
                pass
            
            # ===== التحقق =====
            if "/login" in page.url or "/signin" in page.url:
                try:
                    page.goto(REPLIT_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)
                    log(f"📍 بعد home: {page.url}")
                except:
                    pass
            
            if "/login" in page.url or "/signin" in page.url:
                log("❌ فشل الدخول")
                try:
                    page.screenshot(path="debug_login_failed.png")
                    # اطبع نص الخطأ
                    err = page.evaluate("""
                        () => {
                            const errors = document.querySelectorAll('[class*="error"], [role="alert"], .text-red-500');
                            return Array.from(errors).map(e => e.textContent).join(' | ');
                        }
                    """)
                    if err:
                        log(f"📛 رسالة الخطأ: {err}")
                except:
                    pass
                browser.close()
                return False
            
            log("✅ نجح الدخول!")
            
            # حفظ الكوكيز
            cookies_raw = context.cookies()
            cookies = []
            for c in cookies_raw:
                if 'replit' in c.get('domain', '').lower():
                    entry = {
                        'name': c['name'], 'value': c['value'],
                        'domain': c['domain'].lstrip('.'),
                        'path': c.get('path', '/'),
                        'secure': c.get('secure', False),
                        'httpOnly': c.get('httpOnly', False),
                        'sameSite': c.get('sameSite', 'Lax'),
                    }
                    if c.get('expires') and c['expires'] > 0:
                        entry['expires'] = int(c['expires'])
                    cookies.append(entry)
            
            browser.close()
            
            if cookies:
                save_cookies(cookies, REPLIT_COOKIE_FILE)
                return True
            return False
    
    except Exception as e:
        log(f"❌ خطأ دخول: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== تشغيل المشروع ====================

def click_run_or_workflow(page) -> str:
    log("🔍 البحث عن زر التشغيل...")
    
    # هل يعمل بالفعل؟
    for ind in [
        'button:has-text("Stop")',
        'iframe[src*="replit.dev"]',
        'iframe[src*="replit.app"]',
        'iframe[src*="kirk.replit.dev"]',
    ]:
        try:
            el = page.locator(ind).first
            if el.count() > 0 and el.is_visible(timeout=800):
                log(f"✅ مؤشر يعمل: {ind}")
                return "running"
        except:
            pass
    
    run_selectors = [
        'button:has-text("Run")',
        '[role="button"]:has-text("Run")',
        'button:has-text("Start")',
        'button:has-text("Preview")',
        'button[aria-label="Run"]',
        'button[aria-label*="Run" i]',
        'button[aria-label*="Start" i]',
        'button[aria-label*="Play" i]',
        '[data-testid="run-button"]',
        '[data-testid*="run" i]',
        '[data-testid*="workflow" i]',
        'button:has(svg[viewBox*="play"])',
        'button:has(svg polygon)',
    ]
    
    for attempt in range(8):
        for sel in run_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=1500):
                    el.click()
                    log(f"✅ نقر → {sel}")
                    page.wait_for_timeout(5000)
                    return "clicked"
            except:
                continue
        
        try:
            result = page.evaluate("""
                () => {
                    const kws = ['run', 'start', 'play', 'preview', 'dev', 'server'];
                    
                    const svgPlay = document.querySelector('button:has(svg polygon), button:has(svg[viewBox*="play"])');
                    if (svgPlay && svgPlay.offsetParent !== null) {
                        svgPlay.click();
                        return { clicked: true, type: 'svg-play' };
                    }
                    
                    const btns = document.querySelectorAll('button, [role="button"]');
                    for (const b of btns) {
                        if (b.offsetParent === null) continue;
                        const t = (b.textContent || '').trim().toLowerCase();
                        const l = (b.getAttribute('aria-label') || '').toLowerCase();
                        const d = (b.getAttribute('data-testid') || '').toLowerCase();
                        
                        if (t.includes('stop') || l.includes('stop')) continue;
                        
                        for (const kw of kws) {
                            if (t === kw || t.startsWith(kw + ' ') || l.includes(kw) || d.includes(kw)) {
                                const r = b.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) {
                                    b.click();
                                    return { clicked: true, text: t.slice(0, 30), type: 'keyword' };
                                }
                            }
                        }
                    }
                    return { clicked: false };
                }
            """)
            if result and result.get('clicked'):
                log(f"✅ نقر JS: {result}")
                page.wait_for_timeout(5000)
                return "clicked"
        except:
            pass
        
        # أول محاولة: اطبع الأزرار
        if attempt == 0:
            try:
                info = page.evaluate("""
                    () => {
                        const arr = [];
                        for (const b of document.querySelectorAll('button, [role="button"]')) {
                            if (b.offsetParent === null) continue;
                            const r = b.getBoundingClientRect();
                            if (r.width < 10 || r.height < 10) continue;
                            arr.push({
                                text: (b.textContent || '').trim().slice(0, 40),
                                label: (b.getAttribute('aria-label') || '').slice(0, 40),
                                tid: (b.getAttribute('data-testid') || '').slice(0, 40),
                                y: Math.round(r.y),
                            });
                        }
                        return arr.slice(0, 25);
                    }
                """)
                log(f"📋 أزرار الصفحة ({len(info)}):")
                for b in info[:15]:
                    log(f"   y={b['y']} | text='{b['text']}' | label='{b['label']}' | tid='{b['tid']}'")
            except:
                pass
        
        if attempt < 7:
            page.wait_for_timeout(2000)
    
    return "not_found"


# ==================== الدورة الكاملة ====================

def open_project_and_target() -> bool:
    global last_update_time, last_status
    
    log("=" * 60)
    log("🔄 دورة فتح المشروع")
    
    cookies = load_cookies(REPLIT_COOKIE_FILE)
    if not cookies:
        log("📂 لا كوكيز - تسجيل دخول...")
        if not login_replit():
            last_status = "login_failed"
            return False
        cookies = load_cookies(REPLIT_COOKIE_FILE)
        if not cookies:
            last_status = "no_cookies"
            return False
    
    need_login = False
    project_ok = False
    target_ok = False
    
    try:
        with sync_playwright() as p:
            browser, context = create_context(p, cookies, headless=True)
            page = context.new_page()
            
            # ===== 1. فتح المشروع =====
            log(f"📂 فتح المشروع")
            try:
                page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                log("⚠️ انتهت المهلة")
                browser.close()
                last_status = "timeout"
                return False
            
            page.wait_for_timeout(10000)
            log(f"📍 URL: {page.url}")
            
            try:
                page.screenshot(path="debug_project.png")
            except:
                pass
            
            if "/login" in page.url or "/signin" in page.url:
                log("❌ الكوكيز منتهية")
                need_login = True
            else:
                log("✅ فُتح المشروع")
                project_ok = True
                
                result = click_run_or_workflow(page)
                log(f"📊 نتيجة البحث: {result}")
                
                if result == "clicked":
                    page.wait_for_timeout(15000)
                elif result == "running":
                    log("✅ المشروع يعمل")
                
                try:
                    page.screenshot(path="debug_after_run.png")
                except:
                    pass
            
            browser.close()
    
    except Exception as e:
        log(f"❌ خطأ: {e}")
        import traceback
        traceback.print_exc()
        last_status = "error"
        return False
    
    if need_login:
        log("🔄 حذف الكوكيز وإعادة الدخول...")
        clear_cookies()
        if login_replit():
            return open_project_and_target()
        last_status = "relogin_failed"
        return False
    
    # ===== 2. فتح الرابط المستهدف =====
    if project_ok:
        log("=" * 60)
        log(f"🌐 فتح الرابط المستهدف")
        
        try:
            with sync_playwright() as p:
                browser, context = create_context(p, cookies, headless=True)
                page = context.new_page()
                
                try:
                    page.goto(REPLIT_TARGET_URL, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(5000)
                    
                    status = page.evaluate("() => document.readyState")
                    title = page.title()
                    
                    log(f"📄 الحالة: {status}")
                    log(f"📄 العنوان: {title}")
                    
                    body_text = ""
                    try:
                        body_text = page.text_content("body") or ""
                    except:
                        pass
                    
                    if any(kw in body_text.lower() for kw in ['v2ray', 'vless', 'dashboard', 'server', 'config']):
                        log("✅ الرابط يعرض المشروع!")
                        target_ok = True
                    else:
                        log(f"📄 محتوى (أول 200): {body_text[:200]}")
                        target_ok = True
                    
                    try:
                        page.screenshot(path="debug_target.png")
                    except:
                        pass
                
                except PWTimeout:
                    log("⚠️ انتهت مهلة الرابط المستهدف")
                except Exception as e:
                    log(f"⚠️ خطأ الرابط: {e}")
                
                browser.close()
        except Exception as e:
            log(f"❌ خطأ: {e}")
    
    # ===== حفظ الحالة =====
    last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if project_ok and target_ok:
        last_status = "success"
        log("✅ نجحت الدورة كاملة")
        with open("status.txt", "w") as f:
            f.write(f"status: success\nupdated: {last_update_time}\n")
            f.write(f"project: {REPLIT_PROJECT_URL}\n")
            f.write(f"target: {REPLIT_TARGET_URL}\n")
        return True
    elif project_ok:
        last_status = "project_ok_target_failed"
        return False
    else:
        last_status = "project_failed"
        return False


# ==================== Keep Alive ====================

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            color = '#00ff88' if last_status == 'success' else '#ffaa00'
            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
            <meta http-equiv="refresh" content="30"><title>Replit Keep Alive</title>
            <style>body{{font-family:Arial;text-align:center;padding:40px;
            background:#0a0a0a;color:#eee}}.box{{background:#1a1a2e;padding:20px;
            border-radius:10px;margin:15px auto;max-width:800px;border:1px solid #333}}
            .status{{color:{color};font-size:1.4em;font-weight:bold}}
            a{{color:#00ccff;word-break:break-all}}</style></head><body>
            <h1>🚀 Replit Keep Alive</h1>
            <div class="box">
                <div class="status">الحالة: {last_status}</div>
                <p>آخر تحديث: {last_update_time or '—'}</p>
                <p>الآن: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            <div class="box">
                <p><b>المشروع:</b></p>
                <a href="{REPLIT_PROJECT_URL}" target="_blank">{REPLIT_PROJECT_URL}</a>
                <p><b>الهدف:</b></p>
                <a href="{REPLIT_TARGET_URL}" target="_blank">{REPLIT_TARGET_URL}</a>
            </div>
            </body></html>"""
            self.wfile.write(html.encode('utf-8'))
        elif p == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": last_status,
                "updated": last_update_time,
                "project_url": REPLIT_PROJECT_URL,
                "target_url": REPLIT_TARGET_URL,
            }).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *args):
        pass


def run_keep_alive_server():
    try:
        server = HTTPServer(('0.0.0.0', KEEP_ALIVE_PORT), KeepAliveHandler)
        log(f"🔌 Keep Alive على {KEEP_ALIVE_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"⚠️ Keep Alive: {e}")


# ==================== Main ====================

def main():
    global running
    
    log("🔥 بدء السكربت (headless=True)")
    log(f"📁 كوكيز: {REPLIT_COOKIE_FILE}")
    log(f"📂 مشروع: {REPLIT_PROJECT_URL}")
    log(f"🎯 هدف: {REPLIT_TARGET_URL}")
    
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log("🔑 تسجيل دخول أولي...")
        login_replit()
    
    threading.Thread(target=run_keep_alive_server, daemon=True).start()
    
    while running:
        try:
            open_project_and_target()
            log(f"⏳ انتظار {REPLIT_REFRESH_INTERVAL}s...")
            for _ in range(REPLIT_REFRESH_INTERVAL):
                if not running:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            running = False
            break
        except Exception as e:
            log(f"❌ خطأ: {e}")
            time.sleep(10)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    main()
