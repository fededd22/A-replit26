#!/usr/bin/env python3
"""
Replit Browser Dashboard
- واجهة ويب تفاعلية لمشاهدة والتحكم بالمتصفح
- يعتمد على الكوكيز الجاهزة
"""

import os
import sys
import json
import time
import re
import io
import signal
import base64
import threading
import queue
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
import http.cookiejar

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ==================== الإعدادات ====================
REPLIT_COOKIE_FILE = "cookies.txt"
REPLIT_PROJECT_URL = "https://replit.com/@karimdeka85/v2ray-vless-server-dashboard-5zip"
REPLIT_TARGET_URL = "https://f9732b2f-7002-4f57-b44c-a25d6ab8587c-00-27z973qza9qqb.kirk.replit.dev:443"

WEB_PORT = 8080

# الحالة العامة
state = {
    "status": "idle",
    "message": "في الانتظار...",
    "current_url": "",
    "project_opened": False,
    "target_opened": False,
    "logged_in": False,
    "last_update": None,
    "logs": [],
    "browser_running": False,
}

# قائمة أوامر للتحكم بالمتصفح من الويب
command_queue = queue.Queue()
frame_buffer = {"data": None, "timestamp": None}
frame_lock = threading.Lock()


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    state["logs"].append(line)
    if len(state["logs"]) > 200:
        state["logs"] = state["logs"][-200:]


# ==================== تحميل الكوكيز ====================

def load_cookies(cookie_file):
    if not os.path.exists(cookie_file):
        return []
    
    cookies = []
    try:
        with open(cookie_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if content.startswith(('[', '{')):
            data = json.loads(content)
            if isinstance(data, dict) and 'cookies' in data:
                data = data['cookies']
            for c in data:
                if not isinstance(c, dict): continue
                cookies.append({
                    'name': c.get('name'),
                    'value': c.get('value'),
                    'domain': (c.get('domain') or '.replit.com').lstrip('.'),
                    'path': c.get('path', '/'),
                    'secure': bool(c.get('secure', True)),
                    'httpOnly': bool(c.get('httpOnly', False)),
                    'sameSite': c.get('sameSite', 'Lax') if c.get('sameSite') in ('Strict','Lax','None') else 'Lax',
                })
    except Exception as e:
        log(f"⚠️ خطأ JSON: {e}")
    
    if not cookies:
        try:
            jar = http.cookiejar.MozillaCookieJar(cookie_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            for c in jar:
                cookies.append({
                    'name': c.name, 'value': c.value,
                    'domain': (c.domain or '.replit.com').lstrip('.'),
                    'path': c.path or '/',
                    'secure': bool(c.secure),
                    'httpOnly': bool(c._rest.get('HttpOnly', False)) if hasattr(c, '_rest') else False,
                    'sameSite': 'Lax',
                })
        except Exception as e:
            log(f"⚠️ خطأ Netscape: {e}")
    
    # فلترة replit
    filtered = [c for c in cookies if c.get('name') and c.get('value') and 'replit' in c.get('domain', '').lower()]
    log(f"🍪 {len(filtered)} كوكي Replit من {len(cookies)}")
    return filtered


# ==================== إدارة المتصفح ====================

class BrowserManager:
    """يدير جلسة متصفح واحدة تفاعلية"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.thread = None
        self.stop_flag = threading.Event()
        self.cookies = []
        self.screenshot_thread = None
    
    def start(self, cookies):
        """بدء المتصفح"""
        if self.browser:
            return True
        
        self.cookies = cookies
        
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--window-size=1366,900',
                ],
            )
            
            self.context = self.browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = window.chrome || {};
                window.chrome.runtime = window.chrome.runtime || {};
            """)
            
            if self.cookies:
                try:
                    self.context.add_cookies(self.cookies)
                    log(f"✅ أُضيفت {len(self.cookies)} كوكي")
                except Exception as e:
                    log(f"⚠️ خطأ الكوكيز: {e}")
            
            self.page = self.context.new_page()
            state["browser_running"] = True
            
            # بدء خيط لقطة الشاشة
            self.screenshot_thread = threading.Thread(target=self._screenshot_loop, daemon=True)
            self.screenshot_thread.start()
            
            # بدء خيط معالجة الأوامر
            self.thread = threading.Thread(target=self._command_loop, daemon=True)
            self.thread.start()
            
            log("✅ المتصفح جاهز")
            return True
        
        except Exception as e:
            log(f"❌ فشل تشغيل المتصفح: {e}")
            return False
    
    def _screenshot_loop(self):
        """التقاط لقطات شاشة مستمرة"""
        while not self.stop_flag.is_set():
            try:
                if self.page and not self.page.is_closed():
                    img_bytes = self.page.screenshot(type="jpeg", quality=60, full_page=False)
                    b64 = base64.b64encode(img_bytes).decode('ascii')
                    with frame_lock:
                        frame_buffer["data"] = b64
                        frame_buffer["timestamp"] = time.time()
                    
                    # تحديث الحالة
                    try:
                        state["current_url"] = self.page.url
                        state["logged_in"] = "/login" not in self.page.url and "/signin" not in self.page.url
                    except:
                        pass
            except Exception as e:
                pass
            
            self.stop_flag.wait(0.5)  # كل نصف ثانية
    
    def _command_loop(self):
        """معالجة أوامر التحكم"""
        while not self.stop_flag.is_set():
            try:
                cmd = command_queue.get(timeout=0.5)
                if cmd is None:
                    break
                
                action = cmd.get("action")
                log(f"🎮 أمر: {action}")
                
                try:
                    if action == "goto":
                        url = cmd.get("url")
                        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    
                    elif action == "click":
                        x = cmd.get("x")
                        y = cmd.get("y")
                        self.page.mouse.click(x, y)
                    
                    elif action == "type":
                        text = cmd.get("text")
                        self.page.keyboard.type(text)
                    
                    elif action == "press":
                        key = cmd.get("key")
                        self.page.keyboard.press(key)
                    
                    elif action == "scroll":
                        dy = cmd.get("dy", 300)
                        self.page.mouse.wheel(0, dy)
                    
                    elif action == "back":
                        self.page.go_back()
                    
                    elif action == "forward":
                        self.page.go_forward()
                    
                    elif action == "reload":
                        self.page.reload()
                    
                    elif action == "open_project":
                        self.page.goto(REPLIT_PROJECT_URL, wait_until="domcontentloaded", timeout=60000)
                        state["project_opened"] = True
                    
                    elif action == "open_target":
                        self.page.goto(REPLIT_TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                        state["target_opened"] = True
                    
                    elif action == "close_browser":
                        self.stop()
                        break
                
                except Exception as e:
                    log(f"⚠️ خطأ في الأمر {action}: {e}")
            
            except queue.Empty:
                continue
            except Exception as e:
                log(f"❌ خطأ في معالجة الأوامر: {e}")
    
    def execute(self, action, **kwargs):
        """إرسال أمر للمتصفح"""
        cmd = {"action": action, **kwargs}
        command_queue.put(cmd)
    
    def get_frame(self):
        """الحصول على آخر إطار"""
        with frame_lock:
            return frame_buffer["data"], frame_buffer["timestamp"]
    
    def stop(self):
        """إيقاف المتصفح"""
        self.stop_flag.set()
        try:
            if self.browser:
                self.browser.close()
        except:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except:
            pass
        self.browser = None
        self.context = None
        self.page = None
        state["browser_running"] = False
        log("⏹️ تم إيقاف المتصفح")


# مدير المتصفح العام
browser_mgr = BrowserManager()


# ==================== خادم HTTP ====================

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Replit Browser Dashboard</title>
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
        background: #0a0e17;
        color: #e8eef5;
        height: 100vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }
    header {
        background: linear-gradient(135deg, #1a2332, #0f1720);
        padding: 12px 20px;
        border-bottom: 1px solid #2a3544;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
    }
    h1 {
        font-size: 1.2em;
        color: #00d4ff;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .status-badge {
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85em;
        font-weight: bold;
    }
    .status-idle { background: #555; color: #ccc; }
    .status-running { background: #00c853; color: #000; }
    .status-error { background: #d32f2f; color: #fff; }
    .status-waiting { background: #ff9800; color: #000; }
    
    .toolbar {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        padding: 10px 20px;
        background: #0f1720;
        border-bottom: 1px solid #1e2836;
        align-items: center;
    }
    button, .btn {
        background: #1a2b3d;
        color: #e8eef5;
        border: 1px solid #2a3d54;
        padding: 8px 14px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.9em;
        transition: all 0.2s;
        font-family: inherit;
    }
    button:hover { background: #233a52; border-color: #3d5a7a; }
    button:active { transform: scale(0.97); }
    button.primary { background: #0078d4; border-color: #0088e4; }
    button.primary:hover { background: #0088e4; }
    button.danger { background: #c62828; border-color: #e53935; }
    button.success { background: #2e7d32; border-color: #43a047; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    
    .url-bar {
        flex: 1;
        min-width: 200px;
        padding: 8px 12px;
        background: #0a0e17;
        border: 1px solid #2a3d54;
        border-radius: 6px;
        color: #e8eef5;
        font-family: monospace;
        font-size: 0.85em;
    }
    
    main {
        flex: 1;
        display: flex;
        overflow: hidden;
    }
    
    .browser-area {
        flex: 1;
        background: #000;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
        overflow: hidden;
    }
    
    #browser-frame {
        max-width: 100%;
        max-height: 100%;
        cursor: crosshair;
        user-select: none;
        display: block;
    }
    
    .browser-placeholder {
        color: #555;
        text-align: center;
        padding: 40px;
        font-size: 1.1em;
    }
    
    .sidebar {
        width: 320px;
        background: #0f1720;
        border-right: 1px solid #1e2836;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }
    
    .sidebar-section {
        padding: 12px 16px;
        border-bottom: 1px solid #1e2836;
    }
    .sidebar-title {
        font-size: 0.85em;
        color: #7a8a9a;
        text-transform: uppercase;
        margin-bottom: 8px;
        letter-spacing: 1px;
    }
    .info-row {
        display: flex;
        justify-content: space-between;
        padding: 4px 0;
        font-size: 0.85em;
    }
    .info-label { color: #7a8a9a; }
    .info-value { color: #00d4ff; font-family: monospace; }
    .info-value.ok { color: #00c853; }
    .info-value.err { color: #ff5252; }
    
    .logs {
        flex: 1;
        overflow-y: auto;
        padding: 8px 12px;
        font-family: monospace;
        font-size: 0.75em;
        line-height: 1.5;
        color: #8a9aaa;
        background: #06090f;
    }
    .logs div { padding: 2px 0; border-bottom: 1px solid #0f1720; }
    .logs div:last-child { border-bottom: none; }
    
    .footer-bar {
        padding: 8px 20px;
        background: #0f1720;
        border-top: 1px solid #1e2836;
        font-size: 0.8em;
        color: #7a8a9a;
        display: flex;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
    }
    
    #type-input {
        padding: 8px 12px;
        background: #0a0e17;
        border: 1px solid #2a3d54;
        border-radius: 6px;
        color: #e8eef5;
        flex: 1;
        min-width: 150px;
        font-family: monospace;
    }
    
    @media (max-width: 900px) {
        .sidebar { display: none; }
    }
</style>
</head>
<body>
    <header>
        <h1>🚀 Replit Browser Dashboard</h1>
        <div>
            <span id="status-badge" class="status-badge status-idle">خامل</span>
        </div>
    </header>
    
    <div class="toolbar">
        <button class="success" onclick="startBrowser()" id="btn-start">▶ بدء المتصفح</button>
        <button onclick="cmd('open_project')" id="btn-project">📂 فتح المشروع</button>
        <button onclick="cmd('open_target')" id="btn-target">🌐 فتح الرابط المستهدف</button>
        <button onclick="cmd('reload')">🔄 تحديث</button>
        <button onclick="cmd('back')">◀ رجوع</button>
        <button onclick="cmd('forward')">▶ تقدم</button>
        <button class="danger" onclick="stopBrowser()" id="btn-stop">⏹ إيقاف</button>
    </div>
    
    <div class="toolbar">
        <input class="url-bar" id="url-input" type="text" placeholder="https://..." onkeydown="if(event.key==='Enter')goUrl()">
        <button onclick="goUrl()">اذهب</button>
        <input id="type-input" type="text" placeholder="اكتب هنا ثم Enter..." onkeydown="if(event.key==='Enter')typeText()">
        <button onclick="typeText()">📝 إرسال</button>
    </div>
    
    <main>
        <div class="browser-area" id="browser-area">
            <div class="browser-placeholder" id="placeholder">
                <p>اضغط "▶ بدء المتصفح" للبدء</p>
                <p style="font-size:0.85em;margin-top:10px;color:#444;">
                    ستظهر الصفحة هنا مباشرة
                </p>
            </div>
            <img id="browser-frame" style="display:none;" onclick="clickFrame(event)">
        </div>
        
        <aside class="sidebar">
            <div class="sidebar-section">
                <div class="sidebar-title">الحالة</div>
                <div class="info-row">
                    <span class="info-label">المتصفح:</span>
                    <span class="info-value" id="info-browser">متوقف</span>
                </div>
                <div class="info-row">
                    <span class="info-label">مسجل دخول:</span>
                    <span class="info-value" id="info-login">—</span>
                </div>
                <div class="info-row">
                    <span class="info-label">المشروع:</span>
                    <span class="info-value" id="info-project">—</span>
                </div>
                <div class="info-row">
                    <span class="info-label">الهدف:</span>
                    <span class="info-value" id="info-target">—</span>
                </div>
            </div>
            
            <div class="sidebar-section">
                <div class="sidebar-title">الرابط الحالي</div>
                <div style="font-family:monospace;font-size:0.75em;color:#8a9aaa;word-break:break-all;" id="info-url">—</div>
            </div>
            
            <div class="sidebar-section" style="flex:1;overflow:hidden;display:flex;flex-direction:column;padding-bottom:0;">
                <div class="sidebar-title">السجل</div>
                <div class="logs" id="logs"></div>
            </div>
        </aside>
    </main>
    
    <div class="footer-bar">
        <span>المنفذ: 8080</span>
        <span id="last-update">—</span>
        <span>انقر على الصورة للنقر داخل المتصفح</span>
    </div>
    
<script>
let frameInterval = null;
let lastFrameTime = 0;

function setStatus(text, cls) {
    const el = document.getElementById('status-badge');
    el.textContent = text;
    el.className = 'status-badge status-' + cls;
}

function updateFrame() {
    fetch('/api/frame')
        .then(r => r.json())
        .then(data => {
            if (data.frame && data.timestamp > lastFrameTime) {
                lastFrameTime = data.timestamp;
                const img = document.getElementById('browser-frame');
                const placeholder = document.getElementById('placeholder');
                img.src = 'data:image/jpeg;base64,' + data.frame;
                if (img.style.display === 'none') {
                    img.style.display = 'block';
                    placeholder.style.display = 'none';
                    startFrameLoop();
                }
            }
        })
        .catch(e => {});
}

function startFrameLoop() {
    if (frameInterval) return;
    frameInterval = setInterval(() => {
        fetch('/api/frame')
            .then(r => r.json())
            .then(data => {
                if (data.frame && data.timestamp > lastFrameTime) {
                    lastFrameTime = data.timestamp;
                    document.getElementById('browser-frame').src = 
                        'data:image/jpeg;base64,' + data.frame;
                }
            })
            .catch(e => {});
    }, 700);
}

function updateStatus() {
    fetch('/api/status')
        .then(r => r.json())
        .then(data => {
            document.getElementById('info-browser').textContent = data.browser_running ? 'يعمل' : 'متوقف';
            document.getElementById('info-browser').className = 'info-value ' + (data.browser_running ? 'ok' : 'err');
            
            document.getElementById('info-login').textContent = data.logged_in ? 'نعم ✓' : 'لا';
            document.getElementById('info-login').className = 'info-value ' + (data.logged_in ? 'ok' : 'err');
            
            document.getElementById('info-project').textContent = data.project_opened ? 'مفتوح ✓' : '—';
            document.getElementById('info-project').className = 'info-value ' + (data.project_opened ? 'ok' : '');
            
            document.getElementById('info-target').textContent = data.target_opened ? 'مفتوح ✓' : '—';
            document.getElementById('info-target').className = 'info-value ' + (data.target_opened ? 'ok' : '');
            
            if (data.current_url) {
                document.getElementById('info-url').textContent = data.current_url;
                if (document.activeElement !== document.getElementById('url-input')) {
                    document.getElementById('url-input').value = data.current_url;
                }
            }
            
            document.getElementById('last-update').textContent = 'آخر تحديث: ' + (data.last_update || '—');
            
            const logs = document.getElementById('logs');
            logs.innerHTML = (data.logs || []).slice(-50).map(l => '<div>' + escapeHtml(l) + '</div>').join('');
            logs.scrollTop = logs.scrollHeight;
            
            setStatus(data.browser_running ? 'يعمل' : 'خامل', 
                      data.browser_running ? 'running' : 'idle');
        })
        .catch(e => {});
}

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function cmd(action) {
    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: action})
    });
}

function startBrowser() {
    fetch('/api/start', {method: 'POST'})
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                setTimeout(updateFrame, 2000);
            }
        });
}

function stopBrowser() {
    fetch('/api/stop', {method: 'POST'});
    document.getElementById('browser-frame').style.display = 'none';
    document.getElementById('placeholder').style.display = 'block';
}

function goUrl() {
    const url = document.getElementById('url-input').value.trim();
    if (!url) return;
    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'goto', url: url})
    });
}

function typeText() {
    const text = document.getElementById('type-input').value;
    if (!text) return;
    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'type', text: text})
    });
    document.getElementById('type-input').value = '';
}

function clickFrame(event) {
    const img = event.target;
    const rect = img.getBoundingClientRect();
    const x = (event.clientX - rect.left) * (img.naturalWidth / rect.width);
    const y = (event.clientY - rect.top) * (img.naturalHeight / rect.height);
    
    // رسم نقطة على الصورة للتوضيح
    const dot = document.createElement('div');
    dot.style.position = 'fixed';
    dot.style.left = event.clientX + 'px';
    dot.style.top = event.clientY + 'px';
    dot.style.width = '12px';
    dot.style.height = '12px';
    dot.style.background = '#ff5252';
    dot.style.borderRadius = '50%';
    dot.style.pointerEvents = 'none';
    dot.style.transform = 'translate(-50%,-50%)';
    dot.style.boxShadow = '0 0 10px #ff5252';
    document.body.appendChild(dot);
    setTimeout(() => dot.remove(), 400);
    
    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'click', x: Math.round(x), y: Math.round(y)})
    });
}

// تمرير
document.addEventListener('wheel', (e) => {
    const img = document.getElementById('browser-frame');
    if (e.target !== img) return;
    if (img.style.display === 'none') return;
    e.preventDefault();
    const dy = e.deltaY > 0 ? 300 : -300;
    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'scroll', dy: dy})
    });
}, {passive: false});

// اختصارات لوحة المفاتيح
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    const keys = ['Enter', 'Backspace', 'Tab', 'Escape'];
    if (keys.includes(e.key)) {
        e.preventDefault();
        fetch('/api/command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'press', key: e.key})
        });
    }
});

// بدء
setInterval(updateStatus, 1500);
updateStatus();
updateFrame();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def _send_html(self, html, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/' or path == '/index.html':
            self._send_html(DASHBOARD_HTML)
        
        elif path == '/api/status':
            self._send_json(state)
        
        elif path == '/api/frame':
            frame, ts = browser_mgr.get_frame()
            self._send_json({
                "frame": frame,
                "timestamp": ts or 0,
            })
        
        elif path == '/api/logs':
            self._send_json({"logs": state["logs"][-100:]})
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len) if content_len else b''
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}
        
        if path == '/api/start':
            ok = browser_mgr.start(load_cookies(REPLIT_COOKIE_FILE))
            self._send_json({"ok": ok})
        
        elif path == '/api/stop':
            browser_mgr.stop()
            self._send_json({"ok": True})
        
        elif path == '/api/command':
            action = data.get('action')
            if action:
                kwargs = {k: v for k, v in data.items() if k != 'action'}
                browser_mgr.execute(action, **kwargs)
                self._send_json({"ok": True})
            else:
                self._send_json({"ok": False, "error": "no action"}, 400)
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *args):
        pass


def run_server():
    try:
        server = HTTPServer(('0.0.0.0', WEB_PORT), Handler)
        log(f"🌐 الخادم يعمل على المنفذ {WEB_PORT}")
        log(f"📱 افتح: http://<IP-الخادم>:{WEB_PORT}")
        server.serve_forever()
    except Exception as e:
        log(f"❌ فشل الخادم: {e}")


# ==================== Main ====================

def main():
    global running
    
    log("=" * 60)
    log("🚀 Replit Browser Dashboard")
    log("=" * 60)
    
    # تحقق من الكوكيز
    if not os.path.exists(REPLIT_COOKIE_FILE):
        log(f"❌ ملف {REPLIT_COOKIE_FILE} غير موجود!")
        log("💡 ضع ملف cookies.txt بجانب السكربت")
        sys.exit(1)
    
    cookies = load_cookies(REPLIT_COOKIE_FILE)
    if not cookies:
        log("❌ لا كوكيز Replit صالحة في الملف!")
        sys.exit(1)
    
    log(f"✅ {len(cookies)} كوكي جاهزة")
    
    state["message"] = "اضغط 'بدء المتصفح' من الواجهة"
    state["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # شغّل الخادم
    try:
        run_server()
    except KeyboardInterrupt:
        log("⏹️ إيقاف...")
    finally:
        browser_mgr.stop()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    main()
