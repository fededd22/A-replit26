import asyncio
import os
import re
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
COOKIE_FILE = "cookies.txt"
WEBVIEW_PATTERN = r"https?://[a-f0-9\-]+\.replit\.dev:\d+"


# ===============================
# تحميل كوكيز Replit من ملف Netscape
# ===============================
def load_replit_cookies() -> list:
    if not os.path.exists(COOKIE_FILE):
        print(f"❌ ملف {COOKIE_FILE} غير موجود")
        return []

    jar = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        print(f"❌ خطأ في تحميل الكوكيز: {e}")
        return []

    cookies = []
    for c in jar:
        pw = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path or "/",
            "secure": bool(c.secure),
            "httpOnly": bool(c._rest.get("HttpOnly", False)) if hasattr(c, "_rest") else False,
        }
        if c.expires:
            pw["expires"] = int(c.expires)
        cookies.append(pw)

    print(f"✅ تم تحميل {len(cookies)} كوكي")
    return cookies


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

        # بديل JavaScript
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

        # إذا كان يعمل بالفعل
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
    # 1) من iframe
    try:
        iframes = await page.locator("iframe[src*='replit.dev']").all()
        for iframe in iframes:
            src = await iframe.get_attribute("src") or ""
            m = re.search(WEBVIEW_PATTERN, src)
            if m:
                return m.group(0)
    except Exception:
        pass

    # 2) من نص الصفحة
    try:
        body = await page.text_content("body") or ""
        matches = re.findall(WEBVIEW_PATTERN, body)
        if matches:
            return matches[0]
    except Exception:
        pass

    # 3) JavaScript
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
# العملية الرئيسية: Replit فقط
# ===============================
async def run_replit(chat_id):
    cookies = load_replit_cookies()
    if not cookies:
        await client.send_message(chat_id, f"❌ ملف `{COOKIE_FILE}` غير متوفر.")
        return

    await client.send_message(chat_id, "🌐 𝙊𝙥𝙚𝙣𝙞𝙣𝙜 𝙍𝙚𝙥𝙡𝙞𝙩...")

    temp_dir = tempfile.mkdtemp()
    webview_url = None

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                channel='chrome',
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--window-size=1920,1080'
                ],
                viewport={'width': 1920, 'height': 1080},
                locale='en-US'
            )

            await context.add_cookies(cookies)
            page = context.pages[0] if context.pages else await context.new_page()

            await page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            # التحقق من تسجيل الدخول
            if "/login" in page.url:
                await client.send_message(chat_id, "❌ كوكيز Replit منتهية، حدّث `cookies.txt`.")
                await context.close()
                shutil.rmtree(temp_dir, ignore_errors=True)
                return

            await client.send_message(chat_id, "✅ 𝙇𝙤𝙜𝙜𝙚𝙙 𝙞𝙣 𝙩𝙤 𝙍𝙚𝙥𝙡𝙞𝙩")

            # الضغط على Run
            if await press_run_button(page):
                await client.send_message(chat_id, "▶️ 𝙍𝙪𝙣 𝙥𝙧𝙚𝙨𝙨𝙚𝙙, 𝙬𝙖𝙞𝙩𝙞𝙣𝙜...")
            else:
                await client.send_message(chat_id, "⚠️ 𝙁𝙖𝙞𝙡𝙚𝙙 𝙩𝙤 𝙥𝙧𝙚𝙨𝙨 𝙍𝙪𝙣")

            # استخراج رابط Webview
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

    # إرسال النتيجة
    if webview_url:
        try:
            with open("webview_url.txt", "w") as f:
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
        "🔹 أرسل /run لتشغيل مشروع Replit.\n\n"
        "@AM2_D3"
    )
    await event.reply(welcome_msg)


@client.on(events.NewMessage(pattern=r"^/run$"))
async def run_cmd(event):
    asyncio.create_task(run_replit(event.chat_id))


print("𝙘𝙤𝙣𝙣𝙚𝙘𝙩𝙚𝙙...")
client.run_until_disconnected()
