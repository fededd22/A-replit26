import asyncio
import os
import re
import json
from telethon import TelegramClient, events
from playwright.async_api import async_playwright
import tempfile
import shutil
import http.cookiejar
from datetime import datetime


# ===============================
# إعدادات تلغرام
# ===============================
API_ID = '30687411'
API_HASH = '8fe205c97b03657f280f62832296680f'
BOT_TOKEN = '7848279718:AAHuK4uSPQQfRmwKxi-YbSDh_NGXaVxIjh0'

client = TelegramClient('AM2_D3', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


# ===============================
# إعدادات Replit
# ===============================
REPLIT_PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REPLIT_COOKIE_FILE = "cookies.txt"
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"

# ✅ بيانات تسجيل الدخول
REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"


# ===============================
# أدوات مساعدة
# ===============================
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def netscape_cookie_to_playwright(cookie) -> dict:
    pw = {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path or "/",
        "secure": bool(cookie.secure),
        "httpOnly": bool(cookie._rest.get("HttpOnly", False)) if hasattr(cookie, "_rest") else False,
    }
    if cookie.expires:
        pw["expires"] = int(cookie.expires)
    return pw


def load_replit_cookies() -> list:
    """تحميل كوكيز من cookies.txt (Netscape)"""
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log(f"❌ ملف {REPLIT_COOKIE_FILE} غير موجود")
        return []

    jar = http.cookiejar.MozillaCookieJar(REPLIT_COOKIE_FILE)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        log(f"❌ خطأ في تحميل الكوكيز: {e}")
        return []

    cookies = [netscape_cookie_to_playwright(c) for c in jar]
    log(f"✅ تم تحميل {len(cookies)} كوكي")
    return cookies


def load_replit_cookies_json() -> list:
    """تحميل كوكيز من cookies.txt إذا كان بصيغة JSON (كما في السكريبت الثاني)"""
    if not os.path.exists(REPLIT_COOKIE_FILE):
        return []
    try:
        with open(REPLIT_COOKIE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def clean_cookie(cookie):
    """تنظيف الكوكي وإزالة الحقول غير الصالحة"""
    allowed = ['name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite']
    cleaned = {}
    for field in allowed:
        if field in cookie:
            if field == 'expires':
                if isinstance(cookie[field], (int, float)):
                    cleaned[field] = cookie[field]
                elif isinstance(cookie[field], str):
                    try:
                        dt = datetime.fromisoformat(cookie[field].replace('Z', '+00:00'))
                        cleaned[field] = int(dt.timestamp())
                    except Exception:
                        pass
            elif field in ('httpOnly', 'secure'):
                cleaned[field] = bool(cookie[field])
            elif field == 'sameSite':
                if cookie[field] in ['Strict', 'Lax', 'None']:
                    cleaned[field] = cookie[field]
            else:
                cleaned[field] = str(cookie[field])

    if 'name' not in cleaned or 'value' not in cleaned:
        return None
    if 'domain' in cleaned:
        cleaned['domain'] = cleaned['domain'].lstrip('.')
    return cleaned


# ===============================
# ✅ تسجيل الدخول إلى Replit (async)
# ===============================
async def login_to_replit(chat_id=None) -> bool:
    """تسجيل الدخول إلى Replit بالإيميل وكلمة السر، وحفظ الكوكيز في cookies.txt"""
    log("🔑 تسجيل الدخول إلى Replit...")
    if chat_id:
        await client.send_message(chat_id, "🔑 𝙇𝙤𝙜𝙜𝙞𝙣𝙜 𝙞𝙣 𝙩𝙤 𝙍𝙚𝙥𝙡𝙞𝙩...")

    temp_dir = tempfile.mkdtemp()
    success = False

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                channel='chrome',
                headless=True,   # ✅ headless هنا لأن xvfb قد لا يكون متاحاً
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ],
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale='en-US'
            )

            page = context.pages[0] if context.pages else await context.new_page()

            log("🌐 فتح صفحة تسجيل الدخول...")
            await page.goto("https://replit.com/login", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)

            # ----- إدخال البريد -----
            log("📧 إدخال البريد الإلكتروني...")
            email_filled = False
            email_selectors = [
                "input[type='email']",
                "input[name='username']",
                "input[name='email']",
                "input[placeholder*='mail' i]",
                "input[autocomplete='email']",
            ]
            for sel in email_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible(timeout=2000):
                        await loc.click()
                        await loc.fill(REPLIT_EMAIL)
                        email_filled = True
                        log(f"✅ تم إدخال البريد عبر: {sel}")
                        break
                except Exception:
                    continue

            if not email_filled:
                # محاولة عبر JavaScript
                try:
                    await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('input[type="email"], input[name="username"], input[name="email"]');
                            if (el) {{
                                el.focus();
                                el.value = '{REPLIT_EMAIL}';
                                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        }}
                    """)
                    email_filled = True
                    log("✅ تم إدخال البريد عبر JavaScript")
                except Exception as e:
                    log(f"⚠️ فشل إدخال البريد: {e}")

            await page.wait_for_timeout(1500)

            # ----- إدخال كلمة المرور -----
            log("🔒 إدخال كلمة المرور...")
            pass_filled = False
            pass_selectors = [
                "input[type='password']",
                "input[name='password']",
            ]
            for sel in pass_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible(timeout=2000):
                        await loc.click()
                        await loc.fill(REPLIT_PASSWORD)
                        pass_filled = True
                        log(f"✅ تم إدخال كلمة المرور عبر: {sel}")
                        break
                except Exception:
                    continue

            if not pass_filled:
                try:
                    await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('input[type="password"]');
                            if (el) {{
                                el.focus();
                                el.value = '{REPLIT_PASSWORD}';
                                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        }}
                    """)
                    pass_filled = True
                    log("✅ تم إدخال كلمة المرور عبر JavaScript")
                except Exception as e:
                    log(f"⚠️ فشل إدخال كلمة المرور: {e}")

            await page.wait_for_timeout(1000)

            # ----- الضغط على زر تسجيل الدخول -----
            log("🖱️ الضغط على زر تسجيل الدخول...")
            login_selectors = [
                "button[type='submit']",
                "button:has-text('Log in')",
                "button:has-text('Sign in')",
                "button:has-text('Continue')",
                "button:has-text('Login')",
            ]
            for sel in login_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible(timeout=1500):
                        await btn.click()
                        log(f"✅ تم الضغط على: {sel}")
                        break
                except Exception:
                    continue

            # انتظار ما بعد تسجيل الدخول
            await page.wait_for_timeout(6000)

            current_url = page.url
            log(f"📍 URL الحالي: {current_url}")

            if "login" in current_url and "/login" in current_url:
                log("❌ فشل تسجيل الدخول")
                if chat_id:
                    await client.send_message(chat_id, "❌ 𝙁𝙖𝙞𝙡𝙚𝙙 𝙩𝙤 𝙡𝙤𝙜𝙞𝙣 𝙩𝙤 𝙍𝙚𝙥𝙡𝙞𝙩")
            else:
                log("✅ تم تسجيل الدخول بنجاح!")
                if chat_id:
                    await client.send_message(chat_id, "✅ 𝙇𝙤𝙜𝙜𝙚𝙙 𝙞𝙣 𝙨𝙪𝙘𝙘𝙚𝙨𝙨𝙛𝙪𝙡𝙡𝙮")

                # حفظ الكوكيز بصيغة JSON (متوافقة مع load_replit_cookies_json)
                try:
                    cookies = await context.cookies()
                    cleaned_cookies = []
                    for c in cookies:
                        cl = clean_cookie(c)
                        if cl:
                            cleaned_cookies.append(cl)

                    if cleaned_cookies:
                        with open(REPLIT_COOKIE_FILE, "w", encoding="utf-8") as f:
                            json.dump(cleaned_cookies, f, indent=2)
                        log(f"✅ تم حفظ {len(cleaned_cookies)} كوكي في {REPLIT_COOKIE_FILE}")
                        success = True
                except Exception as e:
                    log(f"⚠️ فشل حفظ الكوكيز: {e}")

            await context.close()

        except Exception as e:
            log(f"❌ خطأ في تسجيل الدخول: {e}")
            if chat_id:
                await client.send_message(chat_id, f"❌ خطأ في تسجيل الدخول: {str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    return success


# ===============================
# ✅ تحميل كوكيز موحّد (يدعم JSON و Netscape)
# ===============================
def load_any_cookies() -> list:
    """يحاول أولاً JSON ثم Netscape"""
    # محاولة JSON
    cookies = load_replit_cookies_json()
    if cookies:
        log(f"✅ تم تحميل {len(cookies)} كوكي (JSON)")
        return cookies

    # محاولة Netscape
    return load_replit_cookies()


# ===============================
# الضغط على زر Run
# ===============================
async def press_run_button(page, max_attempts=10):
    for attempt in range(max_attempts):
        await page.wait_for_timeout(1500)

        selectors = [
            "button:has-text('Run')",
            "button[aria-label='Run']",
            "button[aria-label*='Run' i]",
            "[data-testid='run-button']",
            "[data-cy='run-button']",
            "button:has(svg[viewBox*='play'])",
            "header button:has-text('Run')",
        ]

        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_timeout(4000)
                    return True
            except Exception:
                continue

        try:
            result = await page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button');
                    for (let b of buttons) {
                        const t = (b.textContent || '').toLowerCase();
                        const l = (b.getAttribute('aria-label') || '').toLowerCase();
                        if (t.includes('run') || l.includes('run')) {
                            b.click();
                            return 'clicked';
                        }
                    }
                    return 'not_found';
                }
            """)
            if result == 'clicked':
                await page.wait_for_timeout(4000)
                return True
        except Exception:
            pass

        try:
            stop_btn = page.locator("button:has-text('Stop')").first
            if await stop_btn.count() > 0 and await stop_btn.is_visible(timeout=1500):
                return True
        except Exception:
            pass

        if attempt < max_attempts - 1:
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

    return False


# ===============================
# استخراج رابط Webview
# ===============================
async def get_webview_url(page):
    try:
        iframes = await page.locator("iframe[src*='replit.dev']").all()
        for iframe in iframes:
            src = await iframe.get_attribute("src") or ""
            m = re.search(WEBVIEW_PATTERN, src)
            if m:
                return m.group(0)
    except Exception:
        pass

    try:
        body = await page.text_content("body") or ""
        matches = re.findall(WEBVIEW_PATTERN, body)
        if matches:
            return matches[0]
    except Exception:
        pass

    try:
        result = await page.evaluate("""
            () => {
                const text = document.body.innerText || '';
                const m = text.match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                if (m) return m[0];
                const iframes = document.querySelectorAll('iframe');
                for (let f of iframes) {
                    const mm = (f.src || '').match(/https?:\\/\\/[a-f0-9\\-]+\\.replit\\.dev:\\d+/);
                    if (mm) return mm[0];
                }
                return null;
            }
        """)
        if result:
            return result
    except Exception:
        pass

    return None


# ===============================
# ✅ العملية الرئيسية
# ===============================
async def run_replit(chat_id, force_login: bool = False):
    await client.send_message(chat_id, "🌐 𝙊𝙥𝙚𝙣𝙞𝙣𝙜 𝙍𝙚𝙥𝙡𝙞𝙩...")

    # إذا طُلب تسجيل دخول قسري، أو لا يوجد ملف كوكيز
    if force_login or not os.path.exists(REPLIT_COOKIE_FILE):
        ok = await login_to_replit(chat_id)
        if not ok:
            await client.send_message(chat_id, "❌ فشل تسجيل الدخول ولا يمكن المتابعة.")
            return

    cookies = load_any_cookies()
    if not cookies:
        await client.send_message(chat_id, "❌ لا توجد كوكيز، حاول تسجيل الدخول.")
        ok = await login_to_replit(chat_id)
        if not ok:
            return
        cookies = load_any_cookies()
        if not cookies:
            return

    temp_dir = tempfile.mkdtemp()
    webview_url = None

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                channel='chrome',
                headless=True,   # ✅ يعمل بدون X server
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--window-size=1920,1080'
                ],
                viewport={'width': 1920, 'height': 1080},
                locale='en-US'
            )

            # إضافة الكوكيز واحداً واحداً (مع تجاهل الفاشلة)
            added = 0
            for ck in cookies:
                try:
                    await context.add_cookies([ck])
                    added += 1
                except Exception:
                    continue
            log(f"🍪 تم إضافة {added}/{len(cookies)} كوكي")

            page = context.pages[0] if context.pages else await context.new_page()

            await page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            # إذا انتهت الكوكيز → نعيد تسجيل الدخول تلقائياً
            if "/login" in page.url:
                await client.send_message(chat_id, "⚠️ الكوكيز منتهية، إعادة تسجيل الدخول...")
                await context.close()
                shutil.rmtree(temp_dir, ignore_errors=True)

                ok = await login_to_replit(chat_id)
                if not ok:
                    return
                # إعادة التشغيل بجلسة جديدة
                await run_replit(chat_id, force_login=False)
                return

            await client.send_message(chat_id, "✅ 𝙇𝙤𝙜𝙜𝙚𝙙 𝙞𝙣 𝙩𝙤 𝙍𝙚𝙥𝙡𝙞𝙩")

            if await press_run_button(page):
                await client.send_message(chat_id, "▶️ 𝙍𝙪𝙣 𝙥𝙧𝙚𝙨𝙨𝙚𝙙, 𝙬𝙖𝙞𝙩𝙞𝙣𝙜...")
            else:
                await client.send_message(chat_id, "⚠️ 𝙁𝙖𝙞𝙡𝙚𝙙 𝙩𝙤 𝙥𝙧𝙚𝙨𝙨 𝙍𝙪𝙣")

            for _ in range(10):
                webview_url = await get_webview_url(page)
                if webview_url:
                    break
                await page.wait_for_timeout(2000)

            await context.close()

        except Exception as e:
            await client.send_message(chat_id, f"❌ خطأ: {str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    if webview_url:
        try:
            with open("webview_url.txt", "w", encoding="utf-8") as f:
                f.write(f"{webview_url}\n")
                f.write(f"التحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            pass

        await client.send_message(
            chat_id,
            f"✅ **𝙃𝙚𝙧𝙚 𝙞𝙨 𝙮𝙤𝙪𝙧 𝙒𝙚𝙗𝙫𝙞𝙚𝙬 𝙡𝙞𝙣𝙠:**\n\n`{webview_url}`"
        )
    else:
        await client.send_message(chat_id, "⚠️ لم يتم العثور على رابط Webview.")


# ===============================
# الأوامر
# ===============================
@client.on(events.NewMessage(pattern=r"^/start$"))
async def start(event):
    welcome_msg = (
        "**إذا غامَرْتَ في شَرَفٍ مَرُومِ  ***  فَلا تَقنَعْ بما دونَ النّجومِ** ☁️✨\n\n"
        "🔹 `/run` — تشغيل مشروع Replit (يستخدم كوكيز أو يسجّل الدخول تلقائياً)\n"
        "🔹 `/login` — تسجيل دخول جديد بالإيميل وكلمة السر\n"
        "🔹 `/relogin` — حذف الكوكيز وإعادة تسجيل الدخول من الصفر\n\n"
        "@AM2_D3"
    )
    await event.reply(welcome_msg)


@client.on(events.NewMessage(pattern=r"^/run$"))
async def run_cmd(event):
    asyncio.create_task(run_replit(event.chat_id))


@client.on(events.NewMessage(pattern=r"^/login$"))
async def login_cmd(event):
    asyncio.create_task(login_to_replit(event.chat_id))


@client.on(events.NewMessage(pattern=r"^/relogin$"))
async def relogin_cmd(event):
    async def _task():
        try:
            if os.path.exists(REPLIT_COOKIE_FILE):
                os.remove(REPLIT_COOKIE_FILE)
                await client.send_message(event.chat_id, "🗑️ تم حذف الكوكيز القديمة.")
        except Exception:
            pass
        ok = await login_to_replit(event.chat_id)
        if ok:
            await client.send_message(event.chat_id, "✅ جاهز، استخدم `/run` لتشغيل المشروع.")
    asyncio.create_task(_task())


print("𝙘𝙤𝙣𝙣𝙚𝙘𝙩𝙚𝙙...")
client.run_until_disconnected()
