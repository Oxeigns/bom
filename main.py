#!/usr/bin/env python3
"""
SMS Bomber Bot - Main Application (PRODUCTION FIXED)
Python 3.8+  |  Pyrogram 2.x  |  Polling mode

ROOT CAUSE FIX: Client was created at module level but asyncio.run()
creates a new event loop → "Future attached to a different loop" crash.
FIX: Create Client inside main() OR use app.run() pattern.
"""

import os
import sys
import asyncio
import logging
import unicodedata
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Awaitable, Tuple

# ============================================================
# 1.  LOAD .env FIRST
# ============================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================
# 2.  VALIDATE REQUIRED ENV VARS
# ============================================================
_missing = []
if not os.getenv("BOT_TOKEN", "").strip():  _missing.append("BOT_TOKEN")
if not os.getenv("API_ID",    "").strip():  _missing.append("API_ID")
if not os.getenv("API_HASH",  "").strip():  _missing.append("API_HASH")

if _missing:
    sys.exit(
        "\n" + "=" * 55 + "\n"
        "BOT CONFIGURATION ERROR\n"
        "=" * 55 + "\n"
        f"Missing environment variables: {', '.join(_missing)}\n\n"
        "Create a .env file with:\n"
        "  BOT_TOKEN=<from @BotFather>\n"
        "  API_ID=<from my.telegram.org>\n"
        "  API_HASH=<from my.telegram.org>\n"
        "=" * 55
    )

# ============================================================
# 3.  LOGGING
# ============================================================
LOG_FILE = Path(os.getenv("BOT_LOG_PATH", "./logs/bot.log")).expanduser().resolve()

_handlers: list = [logging.StreamHandler(sys.stdout)]
try:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
except (PermissionError, OSError) as _e:
    print(f"[WARN] Cannot create log file at {LOG_FILE}: {_e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)

# ============================================================
# 4.  IMPORT CONFIG
# ============================================================
try:
    from config import (
        bot_config, channel_config, rate_limits,
        MESSAGES, TARGET_ENDPOINTS, ADMIN_IDS,
    )
    logger.info("Config loaded. Endpoints: %d", len(TARGET_ENDPOINTS))
except Exception as _e:
    logger.critical("Failed to import config: %s", _e, exc_info=True)
    sys.exit(1)

# ============================================================
# 5.  IMPORT SMS MODULE
# ============================================================
try:
    from sms import SMSBomber, validate_phone, AttackStats
    logger.info("SMS module loaded.")
except Exception as _e:
    logger.critical("Failed to import sms: %s", _e, exc_info=True)
    sys.exit(1)

# ============================================================
# 6.  IMPORT PYROGRAM  (with all enums)
# ============================================================
try:
    from pyrogram import Client, filters, idle
    from pyrogram.enums import ParseMode, ChatType, ChatMemberStatus
    from pyrogram.types import (
        InlineKeyboardMarkup, InlineKeyboardButton,
        Message, CallbackQuery,
    )
    from pyrogram.errors import (
        UserNotParticipant, FloodWait,
        MessageNotModified, ChatAdminRequired,
    )
    logger.info("Pyrogram imported successfully.")
except ImportError as _e:
    logger.critical("Pyrogram import failed: %s", _e, exc_info=True)
    sys.exit(1)


# ============================================================
# CONSTANTS
# ============================================================
MAX_GLOBAL_COUNT      = 10 ** 12
MAX_TEXT_INPUT_LEN    = 100
MAX_COUNT_INPUT_LEN   = 10
COMMAND_COOLDOWN_SECS = 3

_command_cooldowns: Dict[int, Dict[str, datetime]] = {}


# ============================================================
# INPUT SANITIZATION
# ============================================================

def sanitize_input(text: str, max_length: int = MAX_TEXT_INPUT_LEN) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    filtered = "".join(ch for ch in normalized if ch == "\n" or ord(ch) >= 32)
    return filtered[:max_length].strip()


# ============================================================
# PER-COMMAND RATE LIMITER DECORATOR
# ============================================================

def rate_limit(command_name: str, cooldown_seconds: int = COMMAND_COOLDOWN_SECS):
    def decorator(func: Callable[..., Awaitable[None]]):
        @wraps(func)
        async def wrapper(client: Client, message: Message):
            user = message.from_user
            if not user:
                return await func(client, message)

            now = datetime.now()
            user_limits = _command_cooldowns.setdefault(user.id, {})
            last_used = user_limits.get(command_name)
            if last_used:
                elapsed = (now - last_used).total_seconds()
                if elapsed < cooldown_seconds:
                    wait = max(1, int(cooldown_seconds - elapsed))
                    try:
                        await message.reply_text(f"Wait {wait}s before trying again.")
                    except Exception:
                        pass
                    return

            user_limits[command_name] = now
            return await func(client, message)
        return wrapper
    return decorator


# ============================================================
# SESSION DATA
# ============================================================

class UserSession:
    __slots__ = (
        "user_id", "username", "step", "phone",
        "count", "last_attack", "total_attacks",
        "message_id", "chat_id", "_lock",
    )

    def __init__(self, user_id: int, username: Optional[str] = None):
        self.user_id       = user_id
        self.username      = username
        self.step          = "idle"
        self.phone: Optional[str]        = None
        self.count         = 0
        self.last_attack: Optional[datetime] = None
        self.total_attacks = 0
        self.message_id: Optional[int]   = None
        self.chat_id: Optional[int]      = None
        self._lock         = asyncio.Lock()

    async def set(self, **kwargs):
        async with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k) and k != "_lock":
                    setattr(self, k, v)


# ============================================================
# GLOBAL BOT STATE
# ============================================================

class BotState:
    def __init__(self):
        self.sessions:       Dict[int, UserSession] = {}
        self.active_bombers: Dict[int, SMSBomber]   = {}
        self.cooldowns:      Dict[int, datetime]    = {}
        self.global_count    = 0
        self._lock           = asyncio.Lock()

    def get_session(self, user_id: int, username: Optional[str] = None) -> UserSession:
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id, username=username)
        return self.sessions[user_id]

    async def check_cooldown(self, user_id: int) -> Tuple[bool, str]:
        async with self._lock:
            if user_id in self.cooldowns:
                elapsed     = datetime.now() - self.cooldowns[user_id]
                cooldown_td = timedelta(hours=rate_limits.COOLDOWN_HOURS)
                if elapsed < cooldown_td:
                    remaining  = cooldown_td - elapsed
                    hours, rem = divmod(int(remaining.total_seconds()), 3600)
                    minutes, _ = divmod(rem, 60)
                    return False, f"{hours}h {minutes}m"
                else:
                    del self.cooldowns[user_id]
        return True, ""

    async def set_cooldown(self, user_id: int):
        async with self._lock:
            self.cooldowns[user_id] = datetime.now()

    async def can_start_attack(self) -> bool:
        async with self._lock:
            return len(self.active_bombers) < rate_limits.MAX_CONCURRENT_ATTACKS

    async def try_register_bomber(self, user_id: int, bomber: SMSBomber) -> bool:
        async with self._lock:
            if user_id in self.active_bombers:
                return False
            if len(self.active_bombers) >= rate_limits.MAX_CONCURRENT_ATTACKS:
                return False
            self.active_bombers[user_id] = bomber
            return True

    async def remove_bomber(self, user_id: int):
        async with self._lock:
            self.active_bombers.pop(user_id, None)

    async def add_global_count(self, amount: int):
        async with self._lock:
            self.global_count = min(
                MAX_GLOBAL_COUNT,
                self.global_count + max(0, amount),
            )

    async def cleanup_expired_sessions(self):
        expiry = timedelta(hours=max(1, rate_limits.COOLDOWN_HOURS * 2))
        now = datetime.now()
        async with self._lock:
            expired = [
                uid for uid, ts in self.cooldowns.items()
                if (now - ts) > expiry
            ]
            for uid in expired:
                self.cooldowns.pop(uid, None)
                if uid not in self.active_bombers:
                    self.sessions.pop(uid, None)
        if expired:
            logger.info("Cleanup: removed %d expired sessions.", len(expired))


# ============================================================
# GLOBAL STATE (created at module level - this is fine)
# ============================================================

state = BotState()


# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Attack", callback_data="start_attack")],
        [InlineKeyboardButton("📊 Statistics",   callback_data="stats")],
        [InlineKeyboardButton("❓ Help",          callback_data="help")],
    ])


def verify_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    if channel_config.USERNAME:
        url = "https://t.me/" + channel_config.USERNAME.lstrip("@")
        buttons.append([InlineKeyboardButton("📢 Join Channel", url=url)])
    buttons.append([InlineKeyboardButton("✅ Verify Join", callback_data="verify")])
    buttons.append([InlineKeyboardButton("🔙 Back",        callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Attack", callback_data="cancel")]
    ])


def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 New Attack", callback_data="start_attack")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])


# ============================================================
# SAFE MESSAGE SENDER
# ============================================================

async def safe_reply(message: Message, text: str, reply_markup=None):
    try:
        return await message.reply_text(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning("reply_text failed (trying without parse): %s", e)
        try:
            return await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.DISABLED,
                disable_web_page_preview=True,
            )
        except Exception as e2:
            logger.error("reply_text failed completely: %s", e2)
            return None


async def safe_edit(message: Message, text: str, reply_markup=None):
    try:
        return await message.edit_text(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        return None
    except Exception as e:
        logger.warning("edit_text failed (trying without parse): %s", e)
        try:
            return await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.DISABLED,
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            return None
        except Exception as e2:
            logger.error("edit_text failed completely: %s", e2)
            return None


# ============================================================
# FORCE-JOIN HELPER
# ============================================================

async def check_force_join(client: Client, user_id: int) -> bool:
    if not channel_config.is_configured:
        return True

    try:
        member = await client.get_chat_member(channel_config.ID, user_id)
        if member.status in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT):
            return False
        return True
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        logger.warning("Bot not admin in channel %s — skipping force-join.", channel_config.USERNAME)
        return True
    except Exception as exc:
        logger.error("check_force_join error: %s", exc, exc_info=True)
        return True


async def send_force_join(message: Message):
    text = MESSAGES["FORCE_JOIN"].format(channel=channel_config.USERNAME)
    await safe_reply(message, text, reply_markup=verify_keyboard())


# ============================================================
# ============================================================
#
#   MAIN FUNCTION — Client + Handlers created INSIDE here
#   so they all share the SAME event loop.
#
#   This is the ROOT CAUSE FIX. Previously Client was created
#   at module level, but asyncio.run() creates a new loop,
#   causing "Future attached to a different loop" crash.
#
# ============================================================
# ============================================================

def main():
    """
    Build client, register all handlers, call app.run().
    app.run() internally does: start() → idle() → stop()
    and manages the event loop correctly.
    """

    # ── Create Client INSIDE main ──────────────────────────
    app = Client(
        "sms_bomber_bot",
        api_id    = bot_config.API_ID,
        api_hash  = bot_config.API_HASH,
        bot_token = bot_config.TOKEN,
        workers   = 50,
    )
    logger.info("Pyrogram Client created.")

    # ════════════════════════════════════════════════════════
    # /start COMMAND
    # ════════════════════════════════════════════════════════

    @app.on_message(filters.command("start") & (filters.private | filters.group))
    @rate_limit("start")
    async def cmd_start(client: Client, message: Message):
        user = message.from_user
        if not user:
            return

        try:
            logger.info("/start from user %d (@%s)", user.id, user.username)

            if not await check_force_join(client, user.id):
                await send_force_join(message)
                return

            session = state.get_session(user.id, user.username)
            await session.set(step="idle", phone=None, count=0)

            text = MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS))
            await safe_reply(message, text, reply_markup=main_keyboard())

        except FloodWait as exc:
            logger.warning("/start FloodWait: %ds", exc.value)
            await asyncio.sleep(exc.value)
        except Exception as exc:
            logger.error("/start error: %s", exc, exc_info=True)
            try:
                await safe_reply(message, "Something went wrong. Try /start again.")
            except Exception:
                pass

    # ════════════════════════════════════════════════════════
    # /help COMMAND
    # ════════════════════════════════════════════════════════

    @app.on_message(filters.command("help") & (filters.private | filters.group))
    @rate_limit("help")
    async def cmd_help(client: Client, message: Message):
        user = message.from_user
        if not user:
            return

        try:
            if not await check_force_join(client, user.id):
                await send_force_join(message)
                return

            help_text = (
                "Help - SMS Bomber Bot\n\n"
                "How to use:\n"
                "1. Press Start Attack\n"
                "2. Enter the target phone number\n"
                "3. Enter how many SMS to send\n"
                "4. Watch live progress\n\n"
                "Limits:\n"
                f"- Max {rate_limits.MAX_ATTEMPTS_PER_USER} SMS per attack\n"
                f"- {rate_limits.COOLDOWN_HOURS}h cooldown between attacks\n"
                f"- Max {rate_limits.MAX_CONCURRENT_ATTACKS} simultaneous attacks\n\n"
                "Commands:\n"
                "/start - Start the bot\n"
                "/help - Show this message\n"
                "/stats - Your statistics\n"
                "/admin - Admin panel\n\n"
                "For authorized security testing only."
            )

            kb = main_keyboard() if message.chat.type == ChatType.PRIVATE else None
            await safe_reply(message, help_text, reply_markup=kb)

        except Exception as exc:
            logger.error("/help error: %s", exc, exc_info=True)
            await safe_reply(message, "Error showing help.")

    # ════════════════════════════════════════════════════════
    # /stats COMMAND
    # ════════════════════════════════════════════════════════

    @app.on_message(filters.command("stats") & (filters.private | filters.group))
    @rate_limit("stats")
    async def cmd_stats(client: Client, message: Message):
        user = message.from_user
        if not user:
            return

        try:
            if not await check_force_join(client, user.id):
                await send_force_join(message)
                return

            session = state.get_session(user.id, user.username)
            last_atk = (
                session.last_attack.strftime("%Y-%m-%d %H:%M")
                if session.last_attack else "Never"
            )

            can_go, remaining = await state.check_cooldown(user.id)
            cooldown_str = "None" if can_go else f"{remaining} remaining"

            uname = user.username or "N/A"
            stats_text = (
                f"Your Statistics\n\n"
                f"User: {user.id} (@{uname})\n"
                f"Total Attacks: {session.total_attacks}\n"
                f"Last Target: {session.phone or 'N/A'}\n"
                f"Last Attack: {last_atk}\n"
                f"Cooldown: {cooldown_str}\n\n"
                f"Global:\n"
                f"Active: {len(state.active_bombers)}\n"
                f"Total Sent: {state.global_count}"
            )

            kb = main_keyboard() if message.chat.type == ChatType.PRIVATE else None
            await safe_reply(message, stats_text, reply_markup=kb)

        except Exception as exc:
            logger.error("/stats error: %s", exc, exc_info=True)
            await safe_reply(message, "Error fetching stats.")

    # ════════════════════════════════════════════════════════
    # /admin COMMAND
    # ════════════════════════════════════════════════════════

    @app.on_message(filters.command("admin") & filters.private)
    async def cmd_admin(client: Client, message: Message):
        user = message.from_user
        if not user:
            return

        try:
            if not ADMIN_IDS or user.id not in ADMIN_IDS:
                await safe_reply(message, MESSAGES["UNAUTHORIZED"])
                return

            admin_text = (
                f"Admin Panel\n\n"
                f"Your ID: {user.id}\n"
                f"Active Attacks: {len(state.active_bombers)}\n"
                f"Global SMS Sent: {state.global_count}\n"
                f"Sessions: {len(state.sessions)}\n"
                f"Cooldowns Active: {len(state.cooldowns)}\n\n"
                f"Config:\n"
                f"Channel: {channel_config.USERNAME or 'Not set'}\n"
                f"Admin IDs: {ADMIN_IDS or 'None'}\n"
                f"Max/User: {rate_limits.MAX_ATTEMPTS_PER_USER}\n"
                f"Cooldown: {rate_limits.COOLDOWN_HOURS}h\n"
                f"Concurrent: {rate_limits.MAX_CONCURRENT_ATTACKS}"
            )
            await safe_reply(message, admin_text)

        except Exception as exc:
            logger.error("/admin error: %s", exc, exc_info=True)
            await safe_reply(message, "Error in admin command.")

    # ════════════════════════════════════════════════════════
    # CALLBACK QUERY HANDLER
    # ════════════════════════════════════════════════════════

    @app.on_callback_query()
    async def callback_handler(client: Client, callback_query: CallbackQuery):
        user_id  = callback_query.from_user.id
        username = callback_query.from_user.username
        data     = callback_query.data or ""
        msg      = callback_query.message

        try:
            if data == "verify":
                if await check_force_join(client, user_id):
                    session = state.get_session(user_id, username)
                    await session.set(step="idle")
                    text = MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS))
                    await safe_edit(msg, text, reply_markup=main_keyboard())
                    await callback_query.answer("Verified! Welcome.")
                else:
                    await callback_query.answer(
                        "You haven't joined the channel yet.", show_alert=True
                    )
                return

            if not await check_force_join(client, user_id):
                await callback_query.answer(
                    "Please join the channel first.", show_alert=True
                )
                return

            session = state.get_session(user_id, username)

            if data == "start_attack":
                if user_id in state.active_bombers:
                    await callback_query.answer(
                        "You already have an active attack!", show_alert=True
                    )
                    return

                can_go, remaining = await state.check_cooldown(user_id)
                if not can_go:
                    text = MESSAGES["COOLDOWN"].format(remaining=remaining)
                    await safe_edit(msg, text, reply_markup=main_keyboard())
                    await callback_query.answer()
                    return

                if not await state.can_start_attack():
                    await callback_query.answer(
                        "Server is busy. Try again shortly.", show_alert=True
                    )
                    return

                await session.set(step="phone", phone=None, count=0)
                text = MESSAGES["ENTER_PHONE"]
                await safe_edit(msg, text, reply_markup=back_keyboard())
                await callback_query.answer()

            elif data == "stats":
                last_atk = (
                    session.last_attack.strftime("%Y-%m-%d %H:%M")
                    if session.last_attack else "Never"
                )
                can_go, remaining = await state.check_cooldown(user_id)
                cooldown_str = "None" if can_go else f"{remaining} remaining"

                stats_text = (
                    f"Your Statistics\n\n"
                    f"Total Attacks: {session.total_attacks}\n"
                    f"Last Target: {session.phone or 'N/A'}\n"
                    f"Last Attack: {last_atk}\n"
                    f"Cooldown: {cooldown_str}\n\n"
                    f"Active (global): {len(state.active_bombers)}\n"
                    f"Total Sent (global): {state.global_count}"
                )
                await safe_edit(msg, stats_text, reply_markup=main_keyboard())
                await callback_query.answer()

            elif data == "help":
                await safe_edit(
                    msg,
                    "Help\n\nSend /help for detailed instructions.",
                    reply_markup=main_keyboard(),
                )
                await callback_query.answer()

            elif data == "back":
                await session.set(step="idle")
                text = MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS))
                await safe_edit(msg, text, reply_markup=main_keyboard())
                await callback_query.answer()

            elif data == "cancel":
                if user_id in state.active_bombers:
                    bomber = state.active_bombers[user_id]
                    await bomber.stop()
                    await state.remove_bomber(user_id)

                await session.set(step="idle")
                await safe_edit(msg, "Attack cancelled.", reply_markup=main_keyboard())
                await callback_query.answer("Cancelled.")

            else:
                await callback_query.answer("Unknown action.", show_alert=True)

        except FloodWait as exc:
            logger.warning("FloodWait in callback: %ds", exc.value)
            await asyncio.sleep(exc.value)
        except Exception as exc:
            logger.error("Callback error (data=%r): %s", data, exc, exc_info=True)
            try:
                await callback_query.answer("An error occurred.", show_alert=True)
            except Exception:
                pass

    # ════════════════════════════════════════════════════════
    # TEXT MESSAGE HANDLER (state machine)
    # ════════════════════════════════════════════════════════

    @app.on_message(
        filters.text
        & ~filters.command(["start", "help", "stats", "admin"])
        & (filters.private | filters.group)
    )
    async def text_handler(client: Client, message: Message):
        user = message.from_user
        if not user:
            return
        if user.is_bot:
            return

        try:
            text    = sanitize_input(message.text or "")
            session = state.get_session(user.id, user.username)
            await session.set(chat_id=message.chat.id)

            if not text:
                await safe_reply(message, "Empty input is not allowed.")
                return

            if session.step == "idle":
                if message.chat.type == ChatType.PRIVATE:
                    await safe_reply(
                        message,
                        "Press Start Attack to begin.",
                        reply_markup=main_keyboard(),
                    )
                return

            if not await check_force_join(client, user.id):
                await send_force_join(message)
                return

            if session.step == "phone":
                is_valid, result = validate_phone(text)
                if not is_valid:
                    await safe_reply(
                        message,
                        MESSAGES["ERROR"].format(message=result),
                        reply_markup=back_keyboard(),
                    )
                    return

                await session.set(phone=result, step="count")
                await safe_reply(
                    message,
                    MESSAGES["ENTER_COUNT"].format(
                        max=rate_limits.MAX_ATTEMPTS_PER_USER,
                        cooldown=rate_limits.COOLDOWN_HOURS,
                    ),
                    reply_markup=back_keyboard(),
                )
                return

            if session.step == "count":
                if len(text) > MAX_COUNT_INPUT_LEN:
                    await safe_reply(
                        message,
                        MESSAGES["ERROR"].format(message="Input too long."),
                        reply_markup=back_keyboard(),
                    )
                    return

                try:
                    count = int(text)
                except ValueError:
                    await safe_reply(
                        message,
                        MESSAGES["ERROR"].format(message="Please enter a valid number."),
                        reply_markup=back_keyboard(),
                    )
                    return

                if count < 1 or count > rate_limits.MAX_ATTEMPTS_PER_USER:
                    await safe_reply(
                        message,
                        MESSAGES["ERROR"].format(
                            message=f"Enter a number between 1 and {rate_limits.MAX_ATTEMPTS_PER_USER}."
                        ),
                        reply_markup=back_keyboard(),
                    )
                    return

                if not await state.can_start_attack():
                    await safe_reply(
                        message,
                        "Server is at full capacity. Try again shortly.",
                        reply_markup=back_keyboard(),
                    )
                    return

                await session.set(count=count, step="attacking")

                status_msg = await safe_reply(
                    message,
                    MESSAGES["ATTACK_START"].format(
                        number=session.phone,
                        count=count,
                        endpoints=len(TARGET_ENDPOINTS),
                    ),
                    reply_markup=cancel_keyboard(),
                )

                if status_msg:
                    await session.set(message_id=status_msg.id)
                else:
                    await session.set(step="idle")
                    return

                try:
                    bomber = SMSBomber(
                        phone_number      = session.phone,
                        count             = count,
                        progress_callback = lambda stats, uid=user.id: _update_progress(app, uid, stats),
                    )
                except Exception as exc:
                    logger.error("Failed to create SMSBomber: %s", exc, exc_info=True)
                    await session.set(step="idle")
                    await safe_reply(message, "Failed to initialize attack. Try again.")
                    return

                registered = await state.try_register_bomber(user.id, bomber)
                if not registered:
                    await session.set(step="idle")
                    await safe_reply(
                        message,
                        "You already have an active attack running.",
                        reply_markup=main_keyboard(),
                    )
                    return

                asyncio.create_task(
                    _run_attack(app, user.id, bomber, message.chat.id),
                    name=f"attack_{user.id}",
                )
                return

            if session.step == "attacking":
                await safe_reply(
                    message,
                    "Attack in progress. Use Cancel Attack to stop.",
                    reply_markup=cancel_keyboard(),
                )

        except FloodWait as exc:
            logger.warning("FloodWait in text_handler: %ds", exc.value)
            await asyncio.sleep(exc.value)
        except Exception as exc:
            logger.error("text_handler error: %s", exc, exc_info=True)
            try:
                await safe_reply(message, "An unexpected error occurred.")
            except Exception:
                pass

    # ════════════════════════════════════════════════════════
    # LOG AND RUN
    # ════════════════════════════════════════════════════════

    logger.info("=" * 55)
    logger.info("SMS Bomber Bot — Starting")
    logger.info("  API_ID   : %s",    bot_config.API_ID)
    logger.info("  Token    : %s***", bot_config.TOKEN[:8])
    logger.info("  Endpoints: %d",    len(TARGET_ENDPOINTS))
    logger.info("  ForceJoin: %s",    "Enabled" if channel_config.is_configured else "Disabled")
    logger.info("  Admins   : %s",    ADMIN_IDS or "None")
    logger.info("=" * 55)

    # app.run() does start() → idle() → stop() all in the
    # SAME event loop. No "different loop" error possible.
    app.run()


# ============================================================
# ATTACK HELPERS (accept app as parameter)
# ============================================================

async def _update_progress(app: Client, user_id: int, stats: AttackStats):
    session = state.get_session(user_id)
    if not session.message_id or session.chat_id is None:
        return

    bomber = state.active_bombers.get(user_id)
    if not bomber:
        return

    try:
        await app.edit_message_text(
            chat_id      = session.chat_id,
            message_id   = session.message_id,
            text         = bomber.format_status(),
            reply_markup = cancel_keyboard(),
        )
    except MessageNotModified:
        pass
    except FloodWait:
        pass
    except Exception as exc:
        try:
            await app.edit_message_text(
                chat_id      = session.chat_id,
                message_id   = session.message_id,
                text         = bomber.format_status(),
                reply_markup = cancel_keyboard(),
                parse_mode   = ParseMode.DISABLED,
            )
        except Exception:
            logger.error("Progress update error for user %d: %s", user_id, exc)


async def _run_attack(app: Client, user_id: int, bomber: SMSBomber, chat_id: int):
    session = state.get_session(user_id)

    try:
        stats = await bomber.start()

        async with session._lock:
            session.total_attacks += 1
            session.last_attack    = datetime.now()

        await state.set_cooldown(user_id)
        await state.add_global_count(stats.total)

        complete_text = MESSAGES["ATTACK_COMPLETE"].format(
            number    = session.phone,
            attempted = stats.total,
            success   = stats.success,
            failed    = stats.failed,
            duration  = stats.duration,
            rate      = stats.rate,
        )

        try:
            await app.edit_message_text(
                chat_id      = chat_id,
                message_id   = session.message_id,
                text         = complete_text,
                reply_markup = done_keyboard(),
            )
        except Exception:
            try:
                await app.send_message(
                    chat_id,
                    complete_text,
                    reply_markup=done_keyboard(),
                    parse_mode=ParseMode.DISABLED,
                )
            except Exception as e3:
                logger.error("Could not send completion msg: %s", e3)

    except asyncio.CancelledError:
        logger.info("Attack cancelled for user %d", user_id)
    except Exception as exc:
        logger.error("Attack error for user %d: %s", user_id, exc, exc_info=True)
        try:
            await app.send_message(
                chat_id,
                "An internal error occurred. Please try again.",
                reply_markup=done_keyboard(),
                parse_mode=ParseMode.DISABLED,
            )
        except Exception:
            pass

    finally:
        await session.set(step="idle")
        await state.remove_bomber(user_id)
        logger.info("Attack lifecycle complete for user %d", user_id)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
