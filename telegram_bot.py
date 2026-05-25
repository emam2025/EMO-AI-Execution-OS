import json
import os
import threading
import time
import asyncio
from pathlib import Path

try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ApplicationBuilder
except ImportError:
    Bot = None
    Update = None
    Application = None
    CommandHandler = None
    MessageHandler = None
    filters = None
    ApplicationBuilder = None

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("emo_telegram")


class TelegramBot:
    """Telegram bot integration for EMO AI Orchestrator.

    Features:
    - User authorization via /start
    - Chat with orchestrator via /chat or direct messages
    - System status via /status
    - Help via /help
    - Long message splitting (>4000 chars)
    - Runs in background thread
    """

    MAX_MESSAGE_LENGTH = 4000

    def __init__(self, token="", data_dir=None, brain=None):
        self.token = token
        self.data_dir = Path(data_dir or "/tmp/emo_telegram")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._app = None
        self._running = False
        self._thread = None
        self._brain = brain
        self._authorized_users = set()
        self._load_users()

    def set_brain(self, brain):
        """Set the Brain instance for LLM responses."""
        self._brain = brain

    def _load_users(self):
        path = self.data_dir / "users.json"
        if path.exists():
            try:
                self._authorized_users = set(json.loads(path.read_text()))
            except Exception:
                pass

    def _save_users(self):
        path = self.data_dir / "users.json"
        path.write_text(json.dumps(list(self._authorized_users)))

    @property
    def is_available(self):
        return Application is not None

    def get_status(self):
        if not self.token:
            return {"running": False, "configured": False, "message": "No token set"}
        if not self.is_available:
            return {"running": False, "configured": True, "message": "python-telegram-bot not installed"}
        return {
            "running": self._running,
            "configured": True,
            "users": list(self._authorized_users),
            "message": f"Running with {len(self._authorized_users)} authorized user(s)" if self._running else "Stopped",
        }

    def _get_response(self, text: str) -> str:
        """Get a response from the orchestrator.

        Args:
            text: User message.

        Returns:
            str: AI response.
        """
        if self._brain:
            try:
                return self._brain.ask(user=text)
            except Exception as e:
                logger.error(f"Brain error: {e}")
                return f"❌ Error: {str(e)[:200]}"
        return "❌ Orchestrator not connected."

    def _send_long_message(self, message, text: str):
        """Send a message, splitting if too long.

        Args:
            message: Telegram message object.
            text: Text to send.
        """
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            asyncio.get_event_loop().run_until_complete(
                message.reply_text(text)
            )
        else:
            chunks = [text[i:i + self.MAX_MESSAGE_LENGTH]
                      for i in range(0, len(text), self.MAX_MESSAGE_LENGTH)]
            for i, chunk in enumerate(chunks):
                suffix = f"\n\n✂️ _Part {i + 1}/{len(chunks)}_" if len(chunks) > 1 else ""
                asyncio.get_event_loop().run_until_complete(
                    message.reply_text(chunk + suffix)
                )

    async def _start_handler(self, update: Update, context):
        user = update.effective_user
        if not user:
            return
        uid = str(user.id)
        name = user.full_name or "User"
        self._authorized_users.add(uid)
        self._save_users()
        await update.message.reply_text(
            f"👋 Welcome {name}!\n\n"
            f"✅ You are now authorized to use **Emo AI Orchestrator**.\n\n"
            f"Send me any message and I'll forward it to the orchestrator.\n"
            f"Commands:\n"
            f"  /chat <text> — send a message\n"
            f"  /status — check system status\n"
            f"  /help — show this help"
        )
        logger.info(f"New Telegram user authorized: {user.full_name} (@{user.username}) id={uid}")

    async def _help_handler(self, update: Update, context):
        await update.message.reply_text(
            "🤖 **Emo AI Orchestrator — Telegram Bot**\n\n"
            "Commands:\n"
            "/start — authorize and start\n"
            "/chat <message> — chat with orchestrator\n"
            "/status — system status\n"
            "/help — this message\n\n"
            "Or just send any message directly!"
        )

    async def _status_handler(self, update: Update, context):
        uid = str(update.effective_user.id) if update.effective_user else ""
        is_auth = uid in self._authorized_users
        brain_info = self._brain.get_info() if self._brain else {"provider": "not connected"}
        await update.message.reply_text(
            f"📡 **Emo AI Status**\n\n"
            f"✅ Bot: Running\n"
            f"🤖 Provider: {brain_info.get('provider', 'unknown')}\n"
            f"🧠 Model: {brain_info.get('model', 'unknown')}\n"
            f"👤 Authorized: {'Yes' if is_auth else 'No — use /start'}\n"
            f"💬 Send a message to get started!"
        )

    async def _chat_handler(self, update: Update, context):
        uid = str(update.effective_user.id) if update.effective_user else ""
        if uid not in self._authorized_users:
            await update.message.reply_text("❌ Not authorized. Send /start first.")
            return

        text = update.message.text or ""
        if text.startswith("/chat "):
            text = text[6:].strip()
        if not text:
            await update.message.reply_text("Please send a message.")
            return

        await update.message.reply_text("⏳ Thinking...")

        # Run brain in thread to not block
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._get_response, text)

        await self._send_long_message(update.message, result)
        logger.info(f"Telegram response sent to {uid}")

    async def _echo_handler(self, update: Update, context):
        """Handle non-command messages."""
        uid = str(update.effective_user.id) if update.effective_user else ""
        if uid not in self._authorized_users:
            await update.message.reply_text("❌ Not authorized. Send /start first.")
            return
        text = update.message.text or ""
        if not text.strip():
            return

        await update.message.reply_text("⏳ Thinking...")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._get_response, text)

        await self._send_long_message(update.message, result)

    def start(self):
        if self._running or not self.token or not self.is_available:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._running = True
        logger.info("Telegram bot started in background thread")
        return True

    def stop(self):
        self._running = False
        if self._app:
            try:
                self._app.stop()
            except Exception:
                pass
            self._app = None
        logger.info("Telegram bot stopped")

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            builder = ApplicationBuilder().token(self.token)
            self._app = builder.build()

            self._app.add_handler(CommandHandler("start", self._start_handler))
            self._app.add_handler(CommandHandler("help", self._help_handler))
            self._app.add_handler(CommandHandler("status", self._status_handler))
            self._app.add_handler(CommandHandler("chat", self._chat_handler))
            self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._echo_handler))

            logger.info("Telegram bot polling started")
            self._app.run_polling(stop_signals=[], close_loop=False)
        except Exception as e:
            logger.error(f"Telegram bot error: {e}")
            self._running = False
        finally:
            loop.close()
