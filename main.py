#!/usr/bin/env python3
"""
SMS Bomber Bot - Main Telegram Bot (FIXED VERSION)
Features: Force Join, SMS Bombing, Live Progress Panel
"""

import os
import sys
import logging
import asyncio
import threading
from datetime import datetime
from typing import Dict, Optional

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, FloodWait

# Import local modules
from config import (
    BOT_TOKEN, API_ID, API_HASH, FORCE_JOIN_CHANNEL, FORCE_JOIN_CHANNEL_ID,
    ADMIN_IDS, WELCOME_MESSAGE, FORCE_JOIN_MESSAGE, ENTER_NUMBER_MESSAGE,
    ENTER_ATTEMPTS_MESSAGE, ATTACK_STARTED_MESSAGE, ATTACK_COMPLETE_MESSAGE,
    MAX_ATTEMPTS, MIN_ATTEMPTS, TARGET_SITES
)
from sms import SMSBomber, validate_phone_number

SAFETY_NOTICE = (
    "⚠️ This bot does not support SMS bombing or harassment workflows.\n\n"
    "Use this bot only for lawful automation (e.g., notifications, support, reminders)."
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# User data storage
user_data: Dict[int, Dict] = {}
active_bombers: Dict[int, SMSBomber] = {}
progress_messages: Dict[int, tuple] = {}  # user_id -> (chat_id, message_id)

# Initialize bot
app = Client(
    "sms_bomber_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=100,
    parse_mode="markdown"
)

# ==========================================
# KEYBOARD BUTTONS
# ==========================================

def get_start_keyboard():
    """Get start button keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 START NOW", callback_data="start_bombing")],
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL.replace('@', '')}")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

def get_verify_keyboard():
    """Get verify join keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL.replace('@', '')}")],
        [InlineKeyboardButton("✅ Verify Join", callback_data="verify_join")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
    ])

def get_cancel_keyboard():
    """Get cancel button"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Attack", callback_data="cancel_attack")]
    ])

def get_done_keyboard():
    """Get done/new attack keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 New Attack", callback_data="start_bombing")],
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]
    ])

def get_back_keyboard():
    """Get back button"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
    ])

# ==========================================
# CHECK FORCE JOIN
# ==========================================

async def check_force_join(user_id: int) -> bool:
    """Check if user joined the required channel"""
    try:
        member = await app.get_chat_member(FORCE_JOIN_CHANNEL_ID, user_id)
        return member.status not in ["left", "kicked", "banned"]
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Error checking force join: {e}")
        return False

# ==========================================
# COMMAND HANDLERS
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    # Initialize user data
    if user_id not in user_data:
        user_data[user_id] = {
            "total_attacks": 0,
            "total_sms_sent": 0,
            "step": "idle"
        }
    
    # Check force join
    is_joined = await check_force_join(user_id)
    
    if not is_joined:
        force_text = FORCE_JOIN_MESSAGE.format(channel=FORCE_JOIN_CHANNEL)
        await message.reply_text(
            force_text,
            reply_markup=get_verify_keyboard(),
            disable_web_page_preview=True
        )
        return
    
    # Show welcome message
    welcome_text = WELCOME_MESSAGE.format(
        name=message.from_user.first_name,
        username=message.from_user.username or "N/A"
    )
    
    await message.reply_text(
        welcome_text,
        reply_markup=get_start_keyboard(),
        disable_web_page_preview=True
    )

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message: Message):
    """Handle /help command"""
    help_text = """
╔══════════════════════════════════════════╗
║           📖 HELP GUIDE                  ║
╚══════════════════════════════════════════╝

🔹 Commands:
   /start - Start the bot
   /help - Show this help
   /stats - Show your statistics
   /cancel - Cancel active attack

🔹 How to use:
   1. Click "🚀 START NOW"
   2. Join our channel (required)
   3. Enter target phone number
   4. Enter number of attempts (100-5000)
   5. Watch live progress!

⚠️ Disclaimer: Only use on numbers you own!
"""
    await message.reply_text(help_text, reply_markup=get_back_keyboard())

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message: Message):
    """Handle /stats command"""
    user_id = message.from_user.id
    
    if user_id not in user_data:
        user_data[user_id] = {"total_attacks": 0, "total_sms_sent": 0}
    
    stats_text = f"""
╔══════════════════════════════════════════╗
║           📊 YOUR STATS                  ║
╚══════════════════════════════════════════╝

👤 User: {message.from_user.first_name}
🆔 ID: `{user_id}`

📈 Statistics:
   • Total Attacks: {user_data[user_id].get('total_attacks', 0)}
   • Total SMS Sent: {user_data[user_id].get('total_sms_sent', 0)}
"""
    await message.reply_text(stats_text, reply_markup=get_done_keyboard())

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client, message: Message):
    """Handle /cancel command"""
    user_id = message.from_user.id
    
    if user_id in active_bombers:
        active_bombers[user_id].stop()
        del active_bombers[user_id]
        
        if user_id in progress_messages:
            del progress_messages[user_id]
        
        await message.reply_text(
            "❌ Attack cancelled by user!",
            reply_markup=get_done_keyboard()
        )
    else:
        await message.reply_text(
            "No active attack found!",
            reply_markup=get_start_keyboard()
        )

# ==========================================
# CALLBACK HANDLERS
# ==========================================

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    """Handle callback queries"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    try:
        if data == "start_bombing":
            await callback_query.message.edit_text(
                SAFETY_NOTICE,
                reply_markup=get_back_keyboard(),
                disable_web_page_preview=True
            )
            await callback_query.answer("Feature disabled for safety.", show_alert=True)
        
        elif data == "verify_join":
            is_joined = await check_force_join(user_id)
            
            if is_joined:
                welcome_text = WELCOME_MESSAGE.format(
                    name=callback_query.from_user.first_name,
                    username=callback_query.from_user.username or "N/A"
                )
                await callback_query.message.edit_text(
                    welcome_text,
                    reply_markup=get_start_keyboard(),
                    disable_web_page_preview=True
                )
                await callback_query.answer("✅ Verified successfully!", show_alert=True)
            else:
                await callback_query.answer("❌ You haven't joined yet! Join the channel first.", show_alert=True)
        
        elif data == "back_to_start":
            if user_id in user_data:
                user_data[user_id]["step"] = "idle"
            
            welcome_text = WELCOME_MESSAGE.format(
                name=callback_query.from_user.first_name,
                username=callback_query.from_user.username or "N/A"
            )
            
            await callback_query.message.edit_text(
                welcome_text,
                reply_markup=get_start_keyboard(),
                disable_web_page_preview=True
            )
            await callback_query.answer()
        
        elif data == "help":
            help_text = """
╔══════════════════════════════════════════╗
║           📖 HELP GUIDE                  ║
╚══════════════════════════════════════════╝

🔹 How to use:
   1. Click "🚀 START NOW"
   2. Join our channel (required)
   3. Enter target phone number
   4. Enter number of attempts (100-5000)
   5. Watch live progress!

⚠️ Disclaimer: Only use on numbers you own!
"""
            await callback_query.message.edit_text(
                help_text,
                reply_markup=get_back_keyboard()
            )
            await callback_query.answer()
        
        elif data == "my_stats":
            if user_id not in user_data:
                user_data[user_id] = {"total_attacks": 0, "total_sms_sent": 0}
            
            stats_text = f"""
╔══════════════════════════════════════════╗
║           📊 YOUR STATS                  ║
╚══════════════════════════════════════════╝

👤 User: {callback_query.from_user.first_name}
🆔 ID: `{user_id}`

📈 Statistics:
   • Total Attacks: {user_data[user_id].get('total_attacks', 0)}
   • Total SMS Sent: {user_data[user_id].get('total_sms_sent', 0)}
"""
            await callback_query.message.edit_text(
                stats_text,
                reply_markup=get_done_keyboard()
            )
            await callback_query.answer()
        
        elif data == "cancel_attack":
            if user_id in active_bombers:
                active_bombers[user_id].stop()
                del active_bombers[user_id]
                
                if user_id in progress_messages:
                    del progress_messages[user_id]
                
                await callback_query.message.edit_text(
                    "❌ Attack cancelled by user!",
                    reply_markup=get_done_keyboard()
                )
                await callback_query.answer("Attack cancelled!", show_alert=True)
            else:
                await callback_query.answer("No active attack found!", show_alert=True)
        
    except FloodWait as e:
        await callback_query.answer(f"Please wait {e.value} seconds...", show_alert=True)
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await callback_query.answer("An error occurred! Try again.", show_alert=True)

# ==========================================
# MESSAGE HANDLERS
# ==========================================

@app.on_message(filters.text & filters.private)
async def text_handler(client, message: Message):
    """Handle text messages"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Skip commands
    if text.startswith('/'):
        return
    
    # Check if user has active step
    if user_id not in user_data:
        await message.reply_text(
            "Please start the bot first! Use /start",
            reply_markup=get_start_keyboard()
        )
        return
    
    step = user_data[user_id].get("step", "idle")

    if step == "idle":
        await message.reply_text(
            SAFETY_NOTICE,
            reply_markup=get_back_keyboard(),
            disable_web_page_preview=True
        )
        return
    
    if step == "waiting_number":
        # Validate phone number
        is_valid, result = validate_phone_number(text)
        
        if not is_valid:
            await message.reply_text(
                f"❌ {result}\n\nPlease try again:",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Store phone number
        user_data[user_id]["phone_number"] = result
        user_data[user_id]["step"] = "waiting_attempts"
        
        await message.reply_text(
            ENTER_ATTEMPTS_MESSAGE.format(min=MIN_ATTEMPTS, max=MAX_ATTEMPTS),
            reply_markup=get_back_keyboard()
        )
    
    elif step == "waiting_attempts":
        # Validate attempts
        try:
            attempts = int(text)
            
            if attempts < MIN_ATTEMPTS or attempts > MAX_ATTEMPTS:
                await message.reply_text(
                    f"❌ Please enter a number between {MIN_ATTEMPTS} and {MAX_ATTEMPTS}!",
                    reply_markup=get_back_keyboard()
                )
                return
            
            # Store attempts
            user_data[user_id]["attempts"] = attempts
            user_data[user_id]["step"] = "attacking"
            
            # Start attack
            phone_number = user_data[user_id]["phone_number"]
            
            # Show attack started message
            start_msg = await message.reply_text(
                ATTACK_STARTED_MESSAGE.format(
                    number=phone_number,
                    attempts=attempts,
                    sites=len(TARGET_SITES),
                    threads=5
                ),
                reply_markup=get_cancel_keyboard()
            )
            
            # Store message info for progress updates
            progress_messages[user_id] = (message.chat.id, start_msg.id)
            
            # Initialize bomber
            bomber = SMSBomber(
                phone_number=phone_number,
                total_attempts=attempts,
                progress_callback=None
            )
            
            active_bombers[user_id] = bomber
            
            # Start attack in background using asyncio task instead of thread
            asyncio.create_task(run_attack_async(user_id, bomber, start_msg.id, message.chat.id))
            
        except ValueError:
            await message.reply_text(
                "❌ Please enter a valid number!",
                reply_markup=get_back_keyboard()
            )

# ==========================================
# ATTACK FUNCTIONS (FIXED ASYNC VERSION)
# ==========================================

async def run_attack_async(user_id: int, bomber: SMSBomber, message_id: int, chat_id: int):
    """Run attack and update progress (async version - FIXED)"""
    try:
        # Start the attack in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, bomber.start_attack)
        
        # Update user stats
        if user_id in user_data:
            user_data[user_id]["total_attacks"] = user_data[user_id].get("total_attacks", 0) + 1
            user_data[user_id]["total_sms_sent"] = user_data[user_id].get("total_sms_sent", 0) + bomber.stats["total_sent"]
        
        # Get final stats
        stats = bomber.get_stats()
        
        # Send completion message
        completion_text = ATTACK_COMPLETE_MESSAGE.format(
            number=bomber.phone_number,
            sent=stats["total_sent"],
            success=stats["successful"],
            failed=stats["failed"],
            duration=f"{stats['duration']:.1f}s"
        )
        
        # Edit message with completion
        await edit_message_safe(chat_id, message_id, completion_text)
        
    except Exception as e:
        logger.error(f"Error in attack: {e}")
        await edit_message_safe(
            chat_id, 
            message_id, 
            f"❌ Error during attack: {str(e)}",
            get_done_keyboard()
        )
    finally:
        # Clean up
        if user_id in active_bombers:
            del active_bombers[user_id]
        if user_id in progress_messages:
            del progress_messages[user_id]
        if user_id in user_data:
            user_data[user_id]["step"] = "idle"

async def edit_message_safe(chat_id: int, message_id: int, text: str, reply_markup=None):
    """Safely edit a message"""
    try:
        await app.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup or get_done_keyboard()
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        try:
            await app.send_message(chat_id, text, reply_markup=reply_markup or get_done_keyboard())
        except:
            pass

# ==========================================
# PROGRESS UPDATER (FIXED)
# ==========================================

async def update_progress():
    """Update progress for all active attacks every 3 seconds"""
    while True:
        try:
            for user_id, bomber in list(active_bombers.items()):
                if bomber.stats["is_running"] and user_id in progress_messages:
                    chat_id, message_id = progress_messages[user_id]
                    
                    try:
                        # Get formatted stats
                        stats_text = bomber.format_stats_message()
                        
                        # Edit message with updated stats
                        await app.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=stats_text,
                            reply_markup=get_cancel_keyboard()
                        )
                    except Exception as e:
                        # Message might be the same or other error
                        pass
            
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Error in progress updater: {e}")
            await asyncio.sleep(5)

# ==========================================
# MAIN FUNCTION
# ==========================================

async def main():
    """Main function to run the bot"""
    logger.info("Starting SMS Bomber Bot...")
    
    # Check if config is set
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Please set your BOT_TOKEN in config.py or .env file!")
        sys.exit(1)
    
    # Start the bot
    await app.start()
    
    # Get bot info
    me = await app.get_me()
    logger.info(f"Bot started: @{me.username}")
    
    # Start progress updater
    asyncio.create_task(update_progress())
    
    # Keep the bot running
    await idle()
    
    # Stop the bot
    await app.stop()
    logger.info("Bot stopped!")

if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
