# 🚀 Bot Deployment Checklist

## ✅ **CRITICAL ISSUES RESOLVED**

All blocking issues that prevented the bot from running have been fixed:

### **✅ 1. Package Dependencies Fixed**
- **Issue**: `discord-py>=2.5.2` (incorrect package name)
- **Fix**: Changed to `discord.py>=2.5.2` in `pyproject.toml`
- **Impact**: Discord library will now install correctly

### **✅ 2. Channel ID Constants Fixed**
- **Issue**: `SELL_CHANNEL_ID`, `TRADE_CHANNEL_ID`, etc. undefined in `main.py`
- **Fix**: Added proper imports from `config` module
- **Impact**: Bot won't crash with `NameError` on startup

### **✅ 3. Circular Import Fixed**
- **Issue**: `commands/deal_confirmation.py` importing from `main.py`
- **Fix**: Changed to import directly from `config` module
- **Impact**: No circular import errors during initialization

## 📦 **INSTALLATION REQUIREMENTS**

### **Required Python Packages:**
```bash
pip install discord.py>=2.5.2
pip install mysql-connector-python>=9.3.0
pip install python-dotenv>=1.1.1
pip install aiohttp>=3.12.13
```

**OR using pyproject.toml:**
```bash
pip install -e .
```

### **Required Environment Variables:**
```bash
# Required - Bot will not start without these
DISCORD_BOT_TOKEN=your_discord_bot_token_here
MYSQL_PASSWORD=your_mysql_password_here

# Optional - will use defaults if not set
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_DATABASE=bot_database
MYSQL_PORT=3306
```

## 🗄️ **Database Setup**

### **MySQL Requirements:**
1. **MySQL Server** running and accessible
2. **Database created** (bot will create tables automatically)
3. **User with permissions** to create/modify tables

### **Database Initialization:**
The bot will automatically create all required tables on first run:
- ✅ `user_listings`
- ✅ `sales_data`
- ✅ `active_deals`
- ✅ `deal_confirmations`
- ✅ `active_auctions`
- ✅ `ended_auctions`
- ✅ `active_giveaways`
- ✅ `pending_listings`
- ✅ `support_tickets`
- ✅ `report_tickets`
- ✅ `car_models`
- ✅ `car_listing_stats`
- ✅ `car_listings`
- ✅ `car_price_logs`
- ✅ **`user_ingame_ids`** (NEW - Security System)

## 🤖 **Discord Bot Setup**

### **Required Bot Permissions:**
- ✅ Send Messages
- ✅ Manage Messages
- ✅ Manage Channels
- ✅ Manage Roles
- ✅ Embed Links
- ✅ Attach Files
- ✅ Read Message History
- ✅ Use Slash Commands
- ✅ Create Public Threads
- ✅ Send Messages in Threads

### **Required Discord Server Setup:**
1. **Channels Created** with correct IDs in `config.py`:
   - `#sell-cars` (ID: 1394786079995072704)
   - `#trade-cars` (ID: 1394786078552227861)
   - `#make-auction` (ID: 1394786069534216353)
   - `#auction-house` (ID: 1394800803197354014) - Forum Channel
   - `#make-giveaway` (ID: 1394786061540130879)
   - `#giveaways` (ID: 1394786059635654817)
   - `#support` (ID: 1394786056699641977)
   - `#tradelog` (ID: 1394786041243762729)
   - `#bot` (ID: 1394786046109024428)
   - `#make-sell-trade` (ID: 1394786077180694529)

2. **Member Role Created** (ID: 1394786020842799235)

## 🧪 **Pre-Deployment Testing**

### **Quick Test Commands:**
```bash
# Test configuration loading
python3 -c "from config import config; print(f'Bot token: {config.BOT_TOKEN[:10]}...')"

# Test database functions
python3 -c "from database_mysql import validate_ingame_id_format; print(validate_ingame_id_format('RC463713'))"

# Test logger
python3 -c "from logger_config import log_info; log_info('Test message')"

# Test security system
python3 -c "from security_system import setup_security_monitoring; print('Security system available')"
```

### **Expected Output:**
```
✅ Bot token: your_token...
✅ True
✅ [timestamp] - INFO - Test message
✅ Security system available
```

## 🚀 **Deployment Steps**

### **1. Environment Setup:**
```bash
# Clone/download the repository
git clone https://github.com/TicoHUN/Marketplace-manager.git
cd Marketplace-manager

# Create environment file
cp .env.example .env  # Edit with your values

# Install dependencies
pip install -e .
```

### **2. Configuration:**
```bash
# Set environment variables
export DISCORD_BOT_TOKEN="your_bot_token_here"
export MYSQL_PASSWORD="your_mysql_password"

# OR create .env file:
echo "DISCORD_BOT_TOKEN=your_bot_token_here" > .env
echo "MYSQL_PASSWORD=your_mysql_password" >> .env
```

### **3. Start Bot:**
```bash
python3 main.py
```

### **4. Verify Startup:**
Look for these log messages:
```
✅ Configuration validated successfully
✅ MySQL database initialized successfully
✅ Commands synced successfully! (X commands)
✅ Security monitoring system initialized
✅ Bot initialization complete!
```

## 🛡️ **Security System Features**

### **NEW: Ingame ID Security**
- ✅ **Registration**: Users must provide ingame ID when accepting rules
- ✅ **Validation**: Format validation (2 letters + 6 numbers)
- ✅ **Monitoring**: Real-time detection of ID mismatches in deal channels
- ✅ **Admin Tools**: `/changeid`, `/viewid`, `/listids`, `/deleteid` commands

### **Example Security Alerts:**
When users share wrong ingame IDs in deal channels, the bot automatically sends:
```
🚨 SECURITY ALERT: Ingame ID Mismatch Detected

@User is using a different ingame ID than registered!

Registered ID: RC463713
Used in message: AB123456

⚠️ WARNING SIGNS OF POTENTIAL SCAM:
• User is sharing different ingame ID
• This could be identity theft
• DO NOT PROCEED WITH THIS DEAL
```

## 🔧 **Troubleshooting**

### **Common Issues:**

**1. Bot won't start - Import Error**
```bash
# Check if all packages are installed
pip list | grep -E "discord|mysql|dotenv|aiohttp"

# Reinstall if missing
pip install discord.py mysql-connector-python python-dotenv aiohttp
```

**2. Bot won't start - Config Error**
```bash
# Check environment variables
echo $DISCORD_BOT_TOKEN
echo $MYSQL_PASSWORD

# Verify config loading
python3 -c "from config import config; print('Config OK')"
```

**3. Database Connection Failed**
```bash
# Test MySQL connection
mysql -h localhost -u root -p

# Check database exists
SHOW DATABASES;
```

**4. Commands not appearing**
- ✅ Verify bot has correct permissions
- ✅ Check command sync completed in logs
- ✅ Wait up to 1 hour for Discord to propagate

## ✅ **DEPLOYMENT STATUS: READY**

🟢 **All Critical Issues Resolved**  
🟢 **All Dependencies Correctly Specified**  
🟢 **All Imports Properly Configured**  
🟢 **All Channel IDs Accessible**  
🟢 **Security System Integrated**  
🟢 **Testing Completed Successfully**  

**The bot is now ready for production deployment!** 🎉

---

*Last Updated: After resolving pyproject.toml and channel ID import issues*