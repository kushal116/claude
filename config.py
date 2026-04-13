# config.py — All bot settings in one place

# ── MT5 Credentials ──────────────────────────
# Replace these with your actual MT5 login details
MT5_LOGIN    = 5049200677
MT5_PASSWORD = "!i5sLpYy"
MT5_SERVER   = "MetaQuotes-Demo"

# ── Trading Settings ─────────────────────────
SYMBOL       = "XAUUSD"
TICK_SIZE    = 70          # Volman uses 70-tick bars
RISK_PCT     = 1.0         # Risk 1% of balance per trade

# ── Symbol Settings ──────────────────────────
# XAUUSD: 1 pip = 0.01, pip value = $1 per 0.01 lot (1 oz)
# EURUSD: 1 pip = 0.0001, pip value = $10 per 1 lot
PIP_SIZE     = 0.01        # XAUUSD pip size
PIP_VALUE    = 1.0         # USD per pip per lot for XAUUSD

# ── XAUUSD Volatility Parameters ────────────
# Based on actual data: avg 70-tick bar range ~1400 pips ($14)
# Buildup = relatively tight bars near a level
BUILDUP_MAX_AVG_RANGE    = 1200.0   # Max avg bar range in buildup (pips)
BUILDUP_MAX_SINGLE_BAR   = 2500.0   # Max single bar range (pips)
BUILDUP_MAX_LEVEL_DIST   = 500.0    # Max distance to nearest S/R level (pips)
BUILDUP_MAX_DRIFT        = 1500.0   # Max cluster drift (pips)
LEVEL_CLUSTER_PIPS       = 20.0     # Merge levels within $0.20 of each other
LEVEL_REACTION_THRESHOLD = 10.0     # Within $0.10 counts as "touching" a level
MAX_SPREAD_PIPS          = 25.0     # XAUUSD demo spread can be 15-20 pips

# ── Telegram Bot ─────────────────────────────
# 1. Open Telegram, search for @BotFather
# 2. Send /newbot, follow steps, copy the token
# 3. Send a message to your new bot
# 4. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
# 5. Find your chat_id in the response
TELEGRAM_TOKEN   = "8770127066:AAEiz1KguFs2K6hRn3yU88xv0MQwSv-odAw"
TELEGRAM_CHAT_ID = "778822951"

# ── Database ─────────────────────────────────
DB_PATH = "data/volman.db"
