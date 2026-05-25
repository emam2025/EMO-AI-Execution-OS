#!/usr/bin/env python3
"""
Emo AI System Tray — Cross-platform (macOS, Windows, Linux)

Features:
- Real-time server monitoring
- Safe restart mechanism
- Process ownership validation
- Notification throttling
- Graceful shutdown
- Console fallback mode
- Thread-safe status updates
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import List, Optional

# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
PING_ENDPOINT = f"{SERVER_URL}/api/tray/ping"
POLL_INTERVAL = 5
REQUEST_TIMEOUT = 2
NOTIFICATION_COOLDOWN = 30

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("emo-tray")

# ============================================================
# OPTIONAL IMPORTS
# ============================================================

try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False
    logger.warning("pystray not installed. Falling back to console mode.")
    logger.warning("Install with: pip install pystray Pillow")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not installed. Process validation limited.")

# ============================================================
# ICON GENERATION
# ============================================================

def _create_icon():
    """Create a simple tray icon image."""
    size = 64
    image = Image.new("RGB", (size, size), (30, 30, 60))
    draw = ImageDraw.Draw(image)
    # Draw a circle
    draw.ellipse([8, 8, size - 8, size - 8], fill=(139, 92, 246))
    # Draw "E" text
    draw.text((20, 14), "E", fill=(255, 255, 255))
    return image

# ============================================================
# HELPERS
# ============================================================

def server_alive() -> bool:
    """Check if server responds successfully."""
    try:
        req = urllib.request.Request(PING_ENDPOINT)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            return response.status == 200
    except Exception:
        return False


def is_emo_process(pid: int) -> bool:
    """Verify that PID belongs to Emo AI."""
    if not PSUTIL_AVAILABLE:
        return True
    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline()).lower()
        indicators = ["main.py", "emo", "uvicorn", "fastapi"]
        return any(indicator in cmdline for indicator in indicators)
    except Exception:
        return False


def get_server_pids(port: int = SERVER_PORT) -> List[int]:
    """Find Emo AI server PIDs safely."""
    pids = []
    if not PSUTIL_AVAILABLE:
        return pids
    try:
        for conn in psutil.net_connections(kind="inet"):
            if not conn.laddr:
                continue
            if conn.laddr.port != port:
                continue
            if conn.status != "LISTEN":
                continue
            if not conn.pid:
                continue
            if is_emo_process(conn.pid):
                pids.append(conn.pid)
    except Exception as e:
        logger.error(f"PID scan failed: {e}")
    return list(set(pids))


def terminate_process(pid: int) -> bool:
    """Gracefully terminate process."""
    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"SIGTERM sent to PID {pid}")
        time.sleep(2)
        if PSUTIL_AVAILABLE:
            if psutil.pid_exists(pid):
                logger.warning(f"PID {pid} still alive. Sending SIGKILL.")
                os.kill(pid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return True
    except Exception as e:
        logger.error(f"Failed to terminate PID {pid}: {e}")
        return False


# ============================================================
# NOTIFICATIONS
# ============================================================

_last_notification_time = 0


def notify(title: str, message: str):
    """Send a notification with cooldown."""
    global _last_notification_time
    now = time.time()
    if now - _last_notification_time < NOTIFICATION_COOLDOWN:
        return
    _last_notification_time = now

    # Cross-platform notification
    if sys.platform == "darwin":
        try:
            os.system(f'osascript -e \'display notification "{message}" with title "{title}"\'')
        except Exception:
            logger.info(f"[NOTIFICATION] {title}: {message}")
    elif sys.platform == "win32":
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=3)
        except Exception:
            logger.info(f"[NOTIFICATION] {title}: {message}")
    else:
        logger.info(f"[NOTIFICATION] {title}: {message}")


# ============================================================
# MAIN APP
# ============================================================

class EmoTrayApp:
    """Cross-platform system tray application."""

    def __init__(self):
        if not PYSTRAY_AVAILABLE:
            raise RuntimeError("pystray is required")

        self.lock = threading.RLock()
        self.alive = False
        self.server_process: Optional[subprocess.Popen] = None
        self.running = True
        self.icon_image = _create_icon()

        # Menu items
        self.status_item = pystray.MenuItem(
            "Status: Checking...",
            lambda: None,
            enabled=False
        )
        self.open_item = pystray.MenuItem(
            "Open Dashboard",
            self.open_dashboard
        )
        self.restart_item = pystray.MenuItem(
            "Restart Server",
            self.restart_server
        )
        self.quit_item = pystray.MenuItem(
            "Quit",
            self.quit_app
        )

        self.tray_icon = pystray.Icon(
            "Emo AI",
            self.icon_image,
            menu=pystray.Menu(
                self.status_item,
                pystray.Menu.SEPARATOR,
                self.open_item,
                self.restart_item,
                pystray.Menu.SEPARATOR,
                self.quit_item,
            )
        )

    def open_dashboard(self):
        """Open the web dashboard in browser."""
        try:
            webbrowser.open(SERVER_URL)
        except Exception as e:
            logger.error(f"Failed to open dashboard: {e}")

    def restart_server(self):
        """Restart the Emo AI server."""
        with self.lock:
            logger.info("Restart requested")
            self.status_item.text = "Status: Restarting..."

            # Terminate existing
            pids = get_server_pids()
            for pid in pids:
                terminate_process(pid)
            time.sleep(2)

            # Start new server
            main_py = BASE_DIR / "main.py"
            if not main_py.exists():
                self.status_item.text = "Status: main.py missing"
                notify("Restart Failed", "main.py not found")
                logger.error(f"main.py missing: {main_py}")
                return

            try:
                self.server_process = subprocess.Popen(
                    [sys.executable, str(main_py)],
                    cwd=str(BASE_DIR),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                )
                logger.info(f"Server restarted with PID {self.server_process.pid}")
                time.sleep(3)
                self.update_status()
            except Exception as e:
                logger.error(f"Failed to start server: {e}")
                self.status_item.text = "Status: Start Failed"
                notify("Restart Failed", str(e))

    def update_status(self):
        """Check server status and update tray icon."""
        with self.lock:
            previous = self.alive
            self.alive = server_alive()

            if self.alive:
                self.status_item.text = "Status: Running"
                if not previous:
                    logger.info("Server online")
                    notify("Server Online", "Emo AI server is running")
            else:
                self.status_item.text = "Status: Offline"
                if previous:
                    logger.warning("Server offline")
                    notify("Server Offline", "Emo AI server is not responding")

    def tick(self):
        """Timer callback for status polling."""
        if not self.running:
            return
        try:
            self.update_status()
        except Exception as e:
            logger.error(f"Status update failed: {e}")

    def quit_app(self):
        """Shut down the tray application."""
        logger.info("Tray app shutting down")
        self.running = False
        self.tray_icon.stop()

    def run(self):
        """Start the tray application."""
        logger.info("Starting Emo AI tray app")
        self.update_status()

        # Start polling in background thread
        def poll_loop():
            while self.running:
                time.sleep(POLL_INTERVAL)
                self.tick()

        poll_thread = threading.Thread(target=poll_loop, daemon=True)
        poll_thread.start()

        self.tray_icon.run()


# ============================================================
# CONSOLE MODE
# ============================================================

def simple_mode():
    """Console fallback when pystray is unavailable."""
    print("Emo AI Tray — Console Mode")
    print("Press Ctrl+C to exit\n")

    last = None
    try:
        while True:
            alive = server_alive()
            if alive != last:
                status = "ONLINE" if alive else "OFFLINE"
                print(f"[{time.strftime('%H:%M:%S')}] {status}")
                last = alive
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nExiting...")


# ============================================================
# MAIN
# ============================================================

def main():
    if not PYSTRAY_AVAILABLE:
        simple_mode()
        return

    try:
        app = EmoTrayApp()
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Tray app crashed: {e}")
        simple_mode()


if __name__ == "__main__":
    main()
