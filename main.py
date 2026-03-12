#!/usr/bin/env python3
"""
SMS Bomber Bot - Main Telegram Bot
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
from pyrogram.errors import UserNotParticipant, ChatAdminRequired

# Import local modules
from config import (
    BOT_TOKEN, API_ID, API_HASH, FORCE_JOIN_CHANNEL, FORCE_JOIN_CHANNEL_ID,
    ADMIN_IDS, WELCOME_MESSAGE, FORCE_JOIN_MESSAGE, ENTER_NUMBER_MESSAGE,
    ENTER_ATTEMPTS_MESSAGE, ATTACK_STARTED_MESSAGE, ATTACK_COMPLETE_MESSAGE,
    MAX_ATTEMPTS, MIN_ATTEMPTS, TARGET_SITES
)
from sms import SMSBomber, validate_phone_number

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# User data storage
user_data: Dict[int, Dict] = {}
active_bombers: Dict[int, SMSBomber] = {}

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

async def check_user_joined(user_id: int) -> bool:
    """Check if user joined the required channel"""
    try:
        member = await app.get_chat_member(FORCE_JOIN_CHANNEL_ID, user_id)
        return member.status not in ["left", "kicked"]
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Error checking user membership: {e}")
        return True  # Allow if error

# ==========================================
# COMMAND HANDLERS
# ==========================================

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    # Initialize user data
    user_data[user_id] = {
        "step": "idle",
        "phone_number": None,
        "attempts": None,
        "total_attacks": 0,
        "total_sms_sent": 0
    }
    
    welcome_text = WELCOME_MESSAGE.format(
        name=message.from_user.first_name,
        username=message.from_user.username or "Unknown"
    )
    
    await message.reply_text(
        welcome_text,
        reply_markup=get_start_keyboard(),
        disable_web_page_preview=True
    )

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    """Handle /help command"""
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

🔹 Phone Number Format:
   • +91XXXXXXXXXX ✓
   • 91XXXXXXXXXX ✓
   • XXXXXXXXXX ✓

🔹 Tips:
   • Higher attempts = More SMS
   • Attack runs in background
   • Live stats updated every 3 seconds
   • Indian numbers only (+91)

⚠️ Disclaimer:
   Only use on numbers you own!
   Misuse is strictly prohibited!

🔰 Support: @admin
"""
    await message.reply_text(help_text, reply_markup=get_back_keyboard())

@app.on_message(filters.command("stats"))
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
   • Status: {'✅ Active' if user_id in active_bombers else '⏸ Idle'}

⚡ Bot Status:
   • Sites Available: {len(TARGET_SITES)}
   • Version: 2.0
   • Uptime: 24/7
"""
    await message.reply_text(stats_text, reply_markup=get_back_keyboard())

@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin_command(client, message: Message):
    """Handle /admin command (admin only)"""
    total_users = len(user_data)
    active_attacks = len(active_bombers)
    
    admin_text = f"""
🔰 ADMIN PANEL

📊 Bot Statistics:
   • Total Users: {total_users}
   • Active Attacks: {active_attacks}
   • Total Sites: {len(TARGET_SITES)}

⚙️ Commands:
   /broadcast - Send message to all users
   /ban - Ban a user
   /unban - Unban a user
"""
    await message.reply_text(admin_text)

# ==========================================
# CALLBACK HANDLERS
# ==========================================

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    """Handle all callback queries"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    try:
        if data == "start_bombing":
            # Check force join
            if not await check_user_joined(user_id):
                await callback_query.message.edit_text(
                    FORCE_JOIN_MESSAGE.format(channel=FORCE_JOIN_CHANNEL),
                    reply_markup=get_verify_keyboard(),
                    disable_web_page_preview=True
                )
                return
            
            # Check if already has active attack
            if user_id in active_bombers and active_bombers[user_id].stats["is_running"]:
                await callback_query.answer("⚠️ You already have an active attack!", show_alert=True)
                return
            
            # Initialize user data
            if user_id not in user_data:
                user_data[user_id] = {}
            
            user_data[user_id]["step"] = "waiting_number"
            
            await callback_query.message.edit_text(
                ENTER_NUMBER_MESSAGE,
                reply_markup=get_back_keyboard(),
                disable_web_page_preview=True
            )
        
        elif data == "verify_join":
            # Verify if user joined
            if await check_user_joined(user_id):
                await callback_query.answer("✅ Verified successfully!", show_alert=True)
                
                # Initialize user data
                if user_id not in user_data:
                    user_data[user_id] = {}
                
                user_data[user_id]["step"] = "waiting_number"
                
                await callback_query.message.edit_text(
                    ENTER_NUMBER_MESSAGE,
                    reply_markup=get_back_keyboard(),
                    disable_web_page_preview=True
                )
            else:
                await callback_query.answer("❌ Please join the channel first!", show_alert=True)
        
        elif data == "back_to_start":
            # Reset user step
            if user_id in user_data:
                user_data[user_id]["step"] = "idle"
            
            welcome_text = WELCOME_MESSAGE.format(
                name=callback_query.from_user.first_name,
                username=callback_query.from_user.username or "Unknown"
            )
            
            await callback_query.message.edit_text(
                welcome_text,
                reply_markup=get_start_keyboard(),
                disable_web_page_preview=True
            )
        
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
        
        elif data == "cancel_attack":
            if user_id in active_bombers:
                active_bombers[user_id].stop()
                del active_bombers[user_id]
                
                await callback_query.message.edit_text(
                    "❌ Attack cancelled by user!",
                    reply_markup=get_done_keyboard()
                )
            else:
                await callback_query.answer("No active attack found!", show_alert=True)
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await callback_query.answer("An error occurred!", show_alert=True)

# ==========================================
# MESSAGE HANDLERS
# ==========================================

@app.on_message(filters.text & filters.private)
async def text_handler(client, message: Message):
    """Handle text messages"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Check if user has active step
    if user_id not in user_data:
        await message.reply_text(
            "Please start the bot first!",
            reply_markup=get_start_keyboard()
        )
        return
    
    step = user_data[user_id].get("step", "idle")
    
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
            
            # Initialize bomber
            bomber = SMSBomber(
                phone_number=phone_number,
                total_attempts=attempts,
                progress_callback=None
            )
            
            active_bombers[user_id] = bomber
            
            # Start attack in background
            attack_thread = threading.Thread(
                target=run_attack,
                args=(user_id, bomber, start_msg.message_id, message.chat.id)
            )
            attack_thread.daemon = True
            attack_thread.start()
            
        except ValueError:
            await message.reply_text(
                "❌ Please enter a valid number!",
                reply_markup=get_back_keyboard()
            )

# ==========================================
# ATTACK FUNCTIONS
# ==========================================

def run_attack(user_id: int, bomber: SMSBomber, message_id: int, chat_id: int):
    """Run attack and update progress"""
    try:
        # Start the attack
        bomber.start_attack()
        
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
        
        # Use asyncio to edit message
        asyncio.run(edit_message_safe(chat_id, message_id, completion_text))
        
        # Clean up
        if user_id in active_bombers:
            del active_bombers[user_id]
        
        if user_id in user_data:
            user_data[user_id]["step"] = "idle"
            
    except Exception as e:
        logger.error(f"Error in attack: {e}")
        asyncio.run(edit_message_safe(
            chat_id, 
            message_id, 
            f"❌ Error during attack: {str(e)}",
            get_done_keyboard()
        ))

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
# PROGRESS UPDATER
# ==========================================

# Store message IDs for progress updates
progress_messages: Dict[int, tuple] = {}  # user_id -> (chat_id, message_id)

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
    # Check if config is set
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Please set your BOT_TOKEN in config.py!")
        sys.exit(1)
    
    # Run the bot
    asyncio.run(main())
