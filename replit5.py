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

# ✅ CapSolver (يُستخدم فقط كخطة بديلة عند فشل الكوكيز)
try:
    from capsolver_core import create_capsolver
    CAPSOLVER_AVAILABLE = True
except ImportError:
    CAPSOLVER_AVAILABLE = False


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

# ✅ بيانات تسجيل الدخول (تُستخدم فقط عند /login أو عند فشل الكوكيز)
REPLIT_EMAIL = "karimdeka85@gmail.com"
REPLIT_PASSWORD = "karimdeka92"

# ✅ مفتاح CapSolver (يُستخدم فقط كخطة بديلة)
CAPSOLVER_API_KEY = "CAP-63E69BC05FC9923B039561B8516172F2558DB7A7A2258BF0FD275C042D72A62E"


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


def load_replit_cookies_netscape() -> list:
    """تحميل كوكيز Netscape"""
    if not os.path.exists(REPLIT_COOKIE_FILE):
        return []
    jar = http.cookiejar.MozillaCookieJar(REPLIT_COOKIE_FILE)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        log(f"⚠️ فشل تحميل Netscape: {e}")
        return []
    return [netscape_cookie_to_playwright(c) for c in jar]


def load_replit_cookies_json() -> list:
    """تحميل كوكيز JSON"""
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


def load_any_cookies() -> list:
    """✅ الأولوية: JSON → Netscape"""
    cookies = load_replit_cookies_json()
    if cookies:
        log(f"✅ تم تحميل {len(cookies)} كوكي (JSON)")
        return cookies
    cookies = load_replit_cookies_netscape()
    if cookies:
        log(f"✅ تم تحميل {len(cookies)} كوكي (Netscape)")
        return cookies
    return []


def cookies_file_exists_and_valid() -> bool:
    """التحقق من وجود ملف كوكيز غير فارغ"""
    if not os.path.exists(REPLIT_COOKIE_FILE):
        return False
    if os.path.getsize(REPLIT_COOKIE_FILE) < 50:
        return False
    # التحقق من وجود كوكي جلسة replit على الأقل
    cookies = load_any_cookies()
    if not cookies:
        return False
    # ابحث عن كوكي مهم
    important_names = {"connect.sid", "__Secure-next-auth.session-token", "replit_session", "session"}
    for c in cookies:
        if c.get("name") in important_names:
            return True
    # إذا لم نجد واحداً بالاسم، نقبل الملف إذا كان يحتوي كوكيز replit
    for c in cookies:
        if "replit" in (c.get("domain") or "").lower():
            return True
    return len(cookies) > 0


def clean_cookie(cookie):
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
# حل CAPTCHA (خطة بديلة فقط)
# ===============================
async def solve_captcha_on_page(page, chat_id=None) -> bool:
    if not CAPSOLVER_AVAILABLE or not CAPSOLVER_API_KEY:
        log("⚠️ CapSolver غير متاح")
        return False
    try:
        log("🛡️ محاولة حل CAPTCHA...")
        cap = create_capsolver(api_key=CAPSOLVER_API_KEY, default_timeout=180, polling_interval=5)
        detected = await cap.detect(page)
        if not detected:
            return True
        log(f"🔍 تم اكتشاف: {detected}")
        results = await cap.solve_on_page(page)
        for r in results:
            if r.error:
                log(f"❌ فشل: {r.error}")
                return False
        return True
    except Exception as e:
        log(f"⚠️ خطأ CapSolver: {e}")
        return False


# ===============================
# تسجيل الدخول (يُستدعى فقط عند الضرورة)
# ===============================
async def login_to_replit(chat_id=None) -> bool:
    log("🔑 تسجيل الدخول إلى Replit (خطة بديلة)...")
    if chat_id:
        await client.send_message(chat_id, "🔑 𝙇𝙤𝙜𝙜𝙞𝙣𝙜 𝙞𝙣...")

    temp_dir = tempfile.mkdtemp()
    success = False

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                channel='chrome',
                headless=False,
                args=[
                    '--no-sandbox', '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage', '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ],
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale='en-US'
            )

            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://replit.com/login", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)

            # البريد
            for sel in ["input[name='username']", "input[type='email']", "input[name='email']"]:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible(timeout=2000):
                        await loc.fill(REPLIT_EMAIL)
                        log(f"✅ بريد: {sel}")
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(1200)

            # كلمة المرور
            try:
                pl = page.locator("input[type='password']").first
                await pl.fill(REPLIT_PASSWORD)
                log("✅ كلمة المرور")
            except Exception:
                pass
            await page.wait_for_timeout(1000)

            # حل CAPTCHA إن وُجد
            await solve_captcha_on_page(page, chat_id)

            # زر الدخول
            for sel in ["button[type='submit']", "button:has-text('Log in')", "button:has-text('Sign in')"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible(timeout=1500):
                        await btn.click()
                        log(f"✅ زر: {sel}")
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(8000)
            current_url = page.url

            # محاولة حل CAPTCHA ثانية
            if "/login" in current_url:
                await solve_captcha_on_page(page, chat_id)
                await page.wait_for_timeout(4000)
                current_url = page.url

            if "/login" not in current_url:
                log("✅ تم تسجيل الدخول")
                if chat_id:
                    await client.send_message(chat_id, "✅ 𝙇𝙤𝙜𝙜𝙚𝙙 𝙞𝙣")
                cookies = await context.cookies()
                cleaned = [clean_cookie(c) for c in cookies if clean_cookie(c)]
                with open(REPLIT_COOKIE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cleaned, f, indent=2)
                log(f"✅ حفظ {len(cleaned)} كوكي")
                success = True
            else:
                log("❌ فشل تسجيل الدخول")
                if chat_id:
                    await client.send_message(chat_id, "❌ فشل تسجيل الدخول")

            await context.close()

        except Exception as e:
            log(f"❌ خطأ: {e}")
            if chat_id:
                await client.send_message(chat_id, f"❌ خطأ: {str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    return success


# ===============================
# الضغط على Run
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
                            b.click(); return 'clicked';
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
# استخراج Webview
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
# ✅ العملية الرئيسية (Cookies first)
# ===============================
async def run_replit(chat_id, force_login: bool = False):
    await client.send_message(chat_id, "🌐 𝙊𝙥𝙚𝙣𝙞𝙣𝙜 𝙍𝙚𝙥𝙡𝙞𝙩...")

    # ✅ 1) تحديد المصدر: كوكيز موجودة أم تسجيل دخول؟
    use_cookies = False
    if not force_login and cookies_file_exists_and_valid():
        log("✅ ملف الكوكيز موجود وصالح — سنستخدمه مباشرة")
        await client.send_message(chat_id, "🍪 𝙐𝙨𝙞𝙣𝙜 𝙚𝙭𝙞𝙨𝙩𝙞𝙣𝙜 𝙘𝙤𝙤𝙠𝙞𝙚𝙨...")
        use_cookies = True
    else:
        log("⚠️ لا توجد كوكيز صالحة — سنسجّل الدخول")
        ok = await login_to_replit(chat_id)
        if not ok:
            await client.send_message(chat_id, "❌ فشل تسجيل الدخول.")
            return
        use_cookies = True

    cookies = load_any_cookies()
    if not cookies:
        await client.send_message(chat_id, "❌ لا توجد كوكيز قابلة للاستخدام.")
        return

    temp_dir = tempfile.mkdtemp()
    webview_url = None

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                channel='chrome',
                headless=False,
                args=[
                    '--no-sandbox', '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage', '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars', '--window-size=1920,1080'
                ],
                viewport={'width': 1920, 'height': 1080},
                locale='en-US'
            )

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

            # ✅ 2) إذا فشلت الكوكيز → سجّل الدخول كخطة بديلة
            if "/login" in page.url:
                log("⚠️ الكوكيز منتهية — تفعيل الخطة البديلة (تسجيل دخول)")
                await client.send_message(chat_id, "⚠️ 𝘾𝙤𝙤𝙠𝙞𝙚𝙨 𝙚𝙭𝙥𝙞𝙧𝙚𝙙, 𝙛𝙖𝙡𝙡𝙞𝙣𝙜 𝙗𝙖𝙘𝙠 𝙩𝙤 𝙡𝙤𝙜𝙞𝙣...")
                await context.close()
                shutil.rmtree(temp_dir, ignore_errors=True)

                ok = await login_to_replit(chat_id)
                if not ok:
                    await client.send_message(chat_id, "❌ فشل تسجيل الدخول البديل.")
                    return
                # إعادة التشغيل بالكوكيز الجديدة
                await run_replit(chat_id, force_login=False)
                return

            await client.send_message(chat_id, "✅ 𝙇𝙤𝙜𝙜𝙚𝙙 𝙞𝙣 𝙩𝙤 𝙍𝙚𝙥𝙡𝙞𝙩")

            if await press_run_button(page):
                await client.send_message(chat_id, "▶️ 𝙍𝙪𝙣 𝙥𝙧𝙚𝙨𝙨𝙚𝙙...")
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
# أوامر تلغرام
# ===============================
@client.on(events.NewMessage(pattern=r"^/start$"))
async def start(event):
    welcome_msg = (
        "**إذا غامَرْتَ في شَرَفٍ مَرُومِ  ***  فَلا تَقنَعْ بما دونَ النّجومِ** ☁️✨\n\n"
        "🔹 `/run` — تشغيل المشروع (🍪 كوكيز أولاً)\n"
        "🔹 `/login` — تسجيل دخول يدوي (خطة بديلة)\n"
        "🔹 `/relogin` — حذف الكوكيز + تسجيل دخول جديد\n"
        "🔹 `/cookies` — فحص حالة ملف الكوكيز\n"
        "🔹 `/balance` — رصيد CapSolver\n\n"
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
            await client.send_message(event.chat_id, "✅ جاهز، استخدم `/run`.")
    asyncio.create_task(_task())


@client.on(events.NewMessage(pattern=r"^/cookies$"))
async def cookies_cmd(event):
    async def _task():
        if not os.path.exists(REPLIT_COOKIE_FILE):
            await client.send_message(event.chat_id, "❌ ملف `cookies.txt` غير موجود.")
            return
        size = os.path.getsize(REPLIT_COOKIE_FILE)
        cookies = load_any_cookies()
        valid = cookies_file_exists_and_valid()
        status = "✅ صالح" if valid else "⚠️ غير صالح"
        await client.send_message(
            event.chat_id,
            f"📁 **حالة ملف الكوكيز:**\n"
            f"▪️ الحجم: `{size}` بايت\n"
            f"▪️ عدد الكوكيز: `{len(cookies)}`\n"
            f"▪️ الحالة: {status}"
        )
    asyncio.create_task(_task())


@client.on(events.NewMessage(pattern=r"^/balance$"))
async def balance_cmd(event):
    async def _task():
        if not CAPSOLVER_AVAILABLE:
            await client.send_message(event.chat_id, "❌ capsolver-core غير مثبّت.")
            return
        try:
            cap = create_capsolver(api_key=CAPSOLVER_API_KEY)
            balance = await cap.get_balance()
            await client.send_message(event.chat_id, f"💰 رصيد CapSolver: `${balance}`")
        except Exception as e:
            await client.send_message(event.chat_id, f"❌ خطأ: {str(e)}")
    asyncio.create_task(_task())


print("𝙘𝙤𝙣𝙣𝙚𝙘𝙩𝙚𝙙...")
client.run_until_disconnected()
