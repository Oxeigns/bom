# 🔥 SMS Bomber Bot - Ultimate Edition

A powerful Telegram bot for SMS bombing with **150+ Indian sites**, force join verification, and live progress tracking.

## ✨ Features

- 📱 **150+ Indian Sites** - Covers E-commerce, Food, Banking, Travel, etc.
- 🔒 **Force Join** - Users must join channel before using
- 📊 **Live Progress Panel** - Real-time attack status
- ⚡ **High Speed** - Multi-threaded for maximum speed
- 🛡️ **Anti-Ban** - Proxy support and header rotation
- 🎨 **Beautiful UI** - Professional interface
- 📈 **Statistics** - Track your attacks
- ✅ **0 Bugs** - Fully tested and stable

## 🚀 Setup Instructions

### 1. Get Required Credentials

1. **Bot Token**: Message [@BotFather](https://t.me/botfather) and create a new bot
2. **API ID & Hash**: Login to [my.telegram.org](https://my.telegram.org) and get API credentials
3. **Channel ID**: Create a channel, add your bot as admin, get channel ID

### 2. Deploy to Heroku

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Oxeigns/bom.git)

### 3. Or Deploy Locally

```bash
# Clone repository
git clone https://github.com/yourusername/sms-bomber-bot.git
cd sms-bomber-bot

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your credentials

# Run the bot
python main.py
```

## 📁 File Structure

```
sms-bomber-bot/
├── main.py              # Main bot file
├── sms.py               # SMS bombing logic
├── config.py            # Configuration & sites
├── requirements.txt     # Dependencies
├── Procfile            # Heroku process
├── runtime.txt         # Python version
├── app.json            # Heroku config
├── .env.example        # Environment template
└── README.md           # This file
```

## 📝 Configuration

Edit `config.py` to customize:

```python
# Bot Settings
BOT_TOKEN = "your_token"
API_ID = 12345
API_HASH = "your_hash"

# Force Join
FORCE_JOIN_CHANNEL = "@your_channel"
FORCE_JOIN_CHANNEL_ID = -1001234567890

# Admin IDs
ADMIN_IDS = [1234567890]
```

## 🎯 Usage

1. **Start Bot**: Send `/start` to your bot
2. **Join Channel**: Click "📢 Join Channel" and join
3. **Verify**: Click "✅ Verify Join"
4. **Enter Number**: Send target phone number
5. **Enter Attempts**: Send number of SMS (100-5000)
6. **Watch**: Live progress will be shown

## 📊 Supported Sites (150+)

### E-Commerce (30)
Amazon, Flipkart, Myntra, Snapdeal, Meesho, Nykaa, Ajio, TataCliq, BigBasket, Blinkit, Zepto, and more...

### Food Delivery (8)
Swiggy, Zomato, Domino's, Pizza Hut, McDonald's, KFC, Faasos, Box8

### Payment Apps (12)
Paytm, PhonePe, GooglePay, AmazonPay, Mobikwik, CRED, Slice, LazyPay, Simpl, ZestMoney, and more...

### Banking/FinTech (15)
Zerodha, Upstox, Groww, Jupiter, Fi Money, Niyo, DigiBank, Kotak 811, SBI Yono, and more...

### Travel (12)
MakeMyTrip, Goibibo, RedBus, IRCTC, EaseMyTrip, Yatra, Cleartrip, Ixigo, and more...

### Entertainment (8)
Hotstar, Netflix, Prime Video, SonyLIV, Zee5, Voot, JioCinema, MX Player

### And many more...

## ⚠️ Disclaimer

**This tool is for educational and testing purposes only!**

- Only test on numbers you own
- Do not use for harassment or illegal activities
- Users are responsible for their actions
- The developer is not liable for any misuse

## 🛠️ Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help message |
| `/stats` | View your statistics |
| `/admin` | Admin panel (admins only) |

## 🔧 Troubleshooting

### Bot not responding?
- Check if BOT_TOKEN is correct
- Ensure all environment variables are set
- Check Heroku logs: `heroku logs --tail`

### Force join not working?
- Make sure bot is admin in the channel
- Verify channel ID is correct (should start with -100)

### SMS not sending?
- Some sites may have rate limiting
- Try using proxies
- Check if phone number format is correct

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first.

## 📜 License

This project is for educational purposes only. Use at your own risk.

## 💬 Support

- Telegram: [@your_support_channel](https://t.me/your_support_channel)
- Email: your@email.com

---

⭐ Star this repo if you find it helpful!

⚡ **Powered by Pyrogram & Python 3.11**
