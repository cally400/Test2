import os
import logging
import pickle
import random
import string
import re
import cloudscraper
from datetime import datetime
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ========== تهيئة الإعدادات ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== إعدادات API ichancy ==========
# استخدام القيم من البيئة
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "")
PARENT_ID = os.getenv("PARENT_ID", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# إذا كان التوكن باسم مختلف
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", os.getenv("TOKEN", ""))

# التحقق من المتغيرات المطلوبة
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN is required!")
    logger.error("Please set BOT_TOKEN environment variable")
    exit(1)

# تحذير إذا كانت المتغيرات الأخرى مفقودة (لا نوقف التشغيل لأن البوت قد يعمل جزئياً)
if not AGENT_USERNAME or not AGENT_PASSWORD or not PARENT_ID:
    logger.warning("⚠️  Ichancy API credentials are missing!")
    logger.warning("Some features may not work properly")

ORIGIN = "https://agents.ichancy.com"
SIGNIN_URL = ORIGIN + "/global/api/User/signIn"
CREATE_URL = ORIGIN + "/global/api/Player/registerPlayer"
STATISTICS_URL = ORIGIN + "/global/api/Statistics/getPlayersStatisticsPro"
DEPOSIT_URL = ORIGIN + "/global/api/Player/depositToPlayer"
WITHDRAW_URL = ORIGIN + "/global/api/Player/withdrawFromPlayer"
GET_BALANCE_URL = ORIGIN + "/global/api/Player/getPlayerBalanceById"

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 6.0.1; SM-G532F) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/106.0.5249.126 Mobile Safari/537.36"
)
REFERER = ORIGIN + "/dashboard"

# ========== قاعدة البيانات ==========
class Database:
    def __init__(self):
        # في Railway، استخدم SQLite المحلي
        self.db_path = "ichancy_bot.db"
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # جدول المستخدمين
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    balance REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # جدول حسابات ichancy
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ichancy_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    player_id TEXT,
                    login TEXT UNIQUE,
                    password TEXT,
                    email TEXT,
                    initial_balance REAL DEFAULT 0,
                    created_at TIMESTAMP
                )
            ''')
            
            # جدول المعاملات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    player_id TEXT,
                    type TEXT,
                    amount REAL,
                    status TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error initializing database: {e}")
        finally:
            conn.close()
    
    def add_user(self, user_id: str, username: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
        finally:
            conn.close()
    
    def get_user_balance(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            return 0
        finally:
            conn.close()
    
    def update_user_balance(self, user_id: str, amount: float, operation: str = "add"):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            if not result:
                return False
            
            current_balance = result[0]
            if operation == "add":
                new_balance = current_balance + amount
            elif operation == "subtract":
                if current_balance < amount:
                    return False
                new_balance = current_balance - amount
            else:
                new_balance = amount
            
            cursor.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (new_balance, user_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating user balance: {e}")
            return False
        finally:
            conn.close()
    
    def add_ichancy_account(self, user_id: str, player_id: str, login: str, 
                          password: str, email: str, initial_balance: float = 0):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO ichancy_accounts 
                (user_id, player_id, login, password, email, initial_balance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, player_id, login, password, email, initial_balance, datetime.now()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding ichancy account: {e}")
            return False
        finally:
            conn.close()
    
    def get_ichancy_account(self, user_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM ichancy_accounts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,)
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    "id": result[0],
                    "user_id": result[1],
                    "player_id": result[2],
                    "login": result[3],
                    "password": result[4],
                    "email": result[5],
                    "initial_balance": result[6],
                    "created_at": result[7]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting ichancy account: {e}")
            return None
        finally:
            conn.close()
    
    def get_all_ichancy_logins(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT login FROM ichancy_accounts WHERE login IS NOT NULL")
            results = cursor.fetchall()
            return [r[0] for r in results] if results else []
        except Exception as e:
            logger.error(f"Error getting all logins: {e}")
            return []
        finally:
            conn.close()

# ========== Ichancy API Manager ==========
class IchancyAPI:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
        self.cookie_file = "ichancy_cookies.pkl"
        self.is_logged_in = False
        self.load_cookies()
    
    def load_cookies(self):
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, "rb") as f:
                    self.scraper.cookies.update(pickle.load(f))
            except Exception as e:
                logger.error(f"Error loading cookies: {e}")
    
    def save_cookies(self):
        try:
            with open(self.cookie_file, "wb") as f:
                pickle.dump(self.scraper.cookies, f)
        except Exception as e:
            logger.error(f"Error saving cookies: {e}")
    
    def safe_request(self, method, url, **kwargs):
        """وظيفة آمنة للطلبات مع معالجة الأخطاء"""
        try:
            response = self.scraper.request(method, url, **kwargs)
            
            # محاولة تحويل الرد إلى JSON
            try:
                data = response.json()
                return response, data
            except:
                return response, {"raw_response": response.text[:200]}
                
        except Exception as e:
            logger.error(f"Request error to {url}: {e}")
            return None, {"error": str(e)}
    
    def login_to_agent(self):
        """تسجيل الدخول إلى وكيل Ichancy"""
        if not AGENT_USERNAME or not AGENT_PASSWORD:
            return False, {"error": "Agent credentials not configured"}
        
        payload = {"username": AGENT_USERNAME, "password": AGENT_PASSWORD}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", SIGNIN_URL, json=payload, headers=headers)
        
        if response is None:
            return False, {"error": "Network error"}
        
        if isinstance(data, dict) and data.get("result", False):
            self.save_cookies()
            self.is_logged_in = True
            return True, data
        else:
            error_msg = data.get("error", "Unknown error") if isinstance(data, dict) else "Invalid response"
            return False, {"error": error_msg}
    
    def ensure_login(self):
        """التأكد من تسجيل الدخول"""
        if not self.is_logged_in:
            success, data = self.login_to_agent()
            if not success:
                error_msg = data.get("error", "Login failed") if isinstance(data, dict) else "Login failed"
                raise Exception(f"فشل تسجيل الدخول: {error_msg}")
    
    def with_retry(func):
        """ديكوراتور لإعادة المحاولة"""
        def wrapper(self, *args, **kwargs):
            try:
                self.ensure_login()
                return func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"API error in {func.__name__}: {e}")
                self.is_logged_in = False
                try:
                    self.ensure_login()
                    return func(self, *args, **kwargs)
                except Exception as retry_error:
                    logger.error(f"Retry failed in {func.__name__}: {retry_error}")
                    return {"success": False, "error": str(retry_error)}
        return wrapper
    
    @with_retry
    def create_player_with_credentials(self, login: str, password: str):
        """إنشاء حساب جديد"""
        if not PARENT_ID:
            return {"success": False, "error": "Parent ID not configured"}
        
        email = f"{login}@TSA.com"
        
        # التحقق من توفر الإيميل
        counter = 1
        while self.check_email_exists(email):
            email = f"{login}_{counter}@TSA.com"
            counter += 1
        
        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": PARENT_ID,
                "login": login
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", CREATE_URL, json=payload, headers=headers)
        
        if response is None:
            return {"success": False, "error": "Network error"}
        
        if isinstance(data, dict) and data.get("result", False):
            player_id = self.get_player_id_by_login(login)
            return {
                "success": True,
                "player_id": player_id,
                "email": email,
                "login": login,
                "password": password,
                "data": data
            }
        else:
            # استخراج رسالة الخطأ بأمان
            error_msg = "فشل إنشاء الحساب"
            if isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list) and len(notifications) > 0:
                    if isinstance(notifications[0], dict):
                        error_msg = notifications[0].get("content", error_msg)
            
            return {"success": False, "error": error_msg}
    
    def get_player_id_by_login(self, login: str):
        """الحصول على player_id من خلال login"""
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", STATISTICS_URL, json=payload, headers=headers)
        
        if response is None or not isinstance(data, dict):
            return None
        
        records = data.get("result", {}).get("records", [])
        for record in records:
            if isinstance(record, dict) and record.get("username") == login:
                return record.get("playerId")
        return None
    
    @with_retry
    def deposit_to_player(self, player_id: str, amount: float):
        """إيداع رصيد للحساب"""
        payload = {
            "amount": amount,
            "comment": None,
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", DEPOSIT_URL, json=payload, headers=headers)
        
        if response is None:
            return {"success": False, "error": "Network error"}
        
        if isinstance(data, dict) and data.get("result", False):
            return {
                "success": True,
                "status": response.status_code,
                "data": data
            }
        else:
            error_msg = "فشل الإيداع"
            if isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list) and len(notifications) > 0:
                    if isinstance(notifications[0], dict):
                        error_msg = notifications[0].get("content", error_msg)
            
            return {"success": False, "error": error_msg, "data": data}
    
    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float):
        """سحب رصيد من الحساب"""
        payload = {
            "amount": -amount,
            "comment": None,
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", WITHDRAW_URL, json=payload, headers=headers)
        
        if response is None:
            return {"success": False, "error": "Network error"}
        
        if isinstance(data, dict) and data.get("result", False):
            return {
                "success": True,
                "status": response.status_code,
                "data": data
            }
        else:
            error_msg = "فشل السحب"
            if isinstance(data, dict):
                notifications = data.get("notification", [])
                if notifications and isinstance(notifications, list) and len(notifications) > 0:
                    if isinstance(notifications[0], dict):
                        error_msg = notifications[0].get("content", error_msg)
            
            return {"success": False, "error": error_msg, "data": data}
    
    @with_retry
    def get_player_balance(self, player_id: str):
        """جلب رصيد الحساب"""
        payload = {"playerId": str(player_id)}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", GET_BALANCE_URL, json=payload, headers=headers)
        
        if response is None:
            return {"success": False, "error": "Network error", "balance": 0}
        
        if isinstance(data, dict):
            results = data.get("result", [])
            if isinstance(results, list) and len(results) > 0:
                if isinstance(results[0], dict):
                    balance = results[0].get("balance", 0)
                    return {
                        "success": True,
                        "balance": balance,
                        "status": response.status_code,
                        "data": data
                    }
        
        return {"success": False, "error": "Failed to parse balance", "balance": 0}
    
    def check_email_exists(self, email: str):
        """التحقق من وجود الإيميل"""
        payload = {"page": 1, "pageSize": 100, "filter": {"email": email}}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", STATISTICS_URL, json=payload, headers=headers)
        
        if response is None or not isinstance(data, dict):
            return False
        
        records = data.get("result", {}).get("records", [])
        for record in records:
            if isinstance(record, dict) and record.get("email") == email:
                return True
        return False
    
    def check_player_exists(self, login: str):
        """التحقق من وجود اللاعب"""
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        response, data = self.safe_request("POST", STATISTICS_URL, json=payload, headers=headers)
        
        if response is None or not isinstance(data, dict):
            return False
        
        records = data.get("result", {}).get("records", [])
        for record in records:
            if isinstance(record, dict) and record.get("username") == login:
                return True
        return False

# ========== Telegram Bot ==========
# المتغيرات العامة
active_users = set()
api = IchancyAPI()
db = Database()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت"""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username
    
    # إضافة المستخدم إلى قاعدة البيانات
    db.add_user(user_id, username)
    
    # إنشاء لوحة المفاتيح
    keyboard = [
        [InlineKeyboardButton("🆕 إنشاء حساب جديد", callback_data='create_account')],
        [InlineKeyboardButton("💰 تعبئة الرصيد", callback_data='deposit')],
        [InlineKeyboardButton("💳 سحب الرصيد", callback_data='withdraw')],
        [InlineKeyboardButton("👤 حسابي", callback_data='my_account')],
        [InlineKeyboardButton("📊 رصيدي", callback_data='my_balance')],
        [InlineKeyboardButton("🌐 رابط الموقع", callback_data='site_url')],
        [InlineKeyboardButton("🆘 المساعدة", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 *مرحباً بك في بوت إدارة حسابات Ichancy*

*الخدمات المتاحة:*
• 🆕 إنشاء حساب جديد على Ichancy
• 💰 تعبئة الرصيد للحساب
• 💳 سحب الرصيد من الحساب
• 👤 عرض معلومات حسابك
• 📊 معرفة رصيدك في الموقع

اختر الخدمة المطلوبة من الأزرار أدناه 👇
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض التعليمات"""
    help_text = """
*🆘 التعليمات:*

*إنشاء حساب جديد:*
- اضغط على "إنشاء حساب جديد"
- أدخل اسم المستخدم المطلوب (لاتيني فقط)
- أدخل كلمة المرور (8-11 حرف)
- أدخل مبلغ الشحن الابتدائي (10+ NSP)

*تعبئة الرصيد:*
- اضغط على "تعبئة الرصيد"
- أدخل المبلغ المطلوب (10+ NSP)

*سحب الرصيد:*
- اضغط على "سحب الرصيد"
- أدخل المبلغ المطلوب (10+ NSP)

*الأوامر المتاحة:*
/start - بدء البوت
/help - عرض التعليمات
/balance - عرض رصيدك

*ملاحظات:*
- الحد الأدنى لأي عملية هو 10 NSP
- الرصيد يُحدّث كل 30 دقيقة
- احفظ بيانات حسابك في مكان آمن
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض رصيد المستخدم"""
    user_id = str(update.effective_user.id)
    balance = db.get_user_balance(user_id)
    
    await update.message.reply_text(
        f"💰 *رصيدك الحالي:* {balance} NSP",
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار"""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    chat_id = query.message.chat.id
    
    if query.data == 'create_account':
        # التحقق من تكوين API أولاً
        if not all([AGENT_USERNAME, AGENT_PASSWORD, PARENT_ID]):
            await query.edit_message_text(
                "❌ خدمة إنشاء الحسابات غير متاحة حالياً\n"
                "يرجى المحاولة لاحقاً أو الاتصال بالدعم."
            )
            return
        
        existing = db.get_ichancy_account(user_id)
        if existing:
            await query.edit_message_text(
                "❗ لديك حساب بالفعل!\n"
                f"اسم المستخدم: `{existing['login']}`\n"
                f"الإيميل: `{existing['email']}`",
                parse_mode='Markdown'
            )
            return
        
        await query.edit_message_text(
            "أدخل اسم المستخدم الذي تريده (باستخدام الأحرف اللاتينية فقط):\n"
            "مثال: `john_doe`"
        )
        context.user_data['awaiting'] = 'username'
        context.user_data['step'] = 'create_account'
    
    elif query.data == 'deposit':
        account = db.get_ichancy_account(user_id)
        if not account:
            await query.edit_message_text("❗ لم تنشئ حساباً بعد!")
            return
        
        if not all([AGENT_USERNAME, AGENT_PASSWORD, PARENT_ID]):
            await query.edit_message_text("❌ خدمة الإيداع غير متاحة حالياً")
            return
        
        if chat_id in active_users:
            await query.edit_message_text("⏳ يرجى الانتظار قبل المحاولة مرة أخرى")
            return
        
        active_users.add(chat_id)
        await query.edit_message_text(
            f"💳 *الحساب:* `{account['login']}`\n"
            "أدخل مبلغ الإيداع (الحد الأدنى 10 NSP):",
            parse_mode='Markdown'
        )
        context.user_data['awaiting'] = 'amount'
        context.user_data['step'] = 'deposit'
        context.user_data['player_id'] = account['player_id']
    
    elif query.data == 'withdraw':
        account = db.get_ichancy_account(user_id)
        if not account:
            await query.edit_message_text("❗ لم تنشئ حساباً بعد!")
            return
        
        if not all([AGENT_USERNAME, AGENT_PASSWORD, PARENT_ID]):
            await query.edit_message_text("❌ خدمة السحب غير متاحة حالياً")
            return
        
        if chat_id in active_users:
            await query.edit_message_text("⏳ يرجى الانتظار قبل المحاولة مرة أخرى")
            return
        
        active_users.add(chat_id)
        
        # جلب الرصيد أولاً
        result = api.get_player_balance(account['player_id'])
        if not result['success']:
            await query.edit_message_text("❌ تعذر جلب الرصيد من الموقع")
            active_users.discard(chat_id)
            return
        
        balance = result['balance']
        await query.edit_message_text(
            f"💳 *الحساب:* `{account['login']}`\n"
            f"💰 *الرصيد المتاح:* {balance} NSP\n"
            "أدخل مبلغ السحب (الحد الأدنى 10 NSP):",
            parse_mode='Markdown'
        )
        context.user_data['awaiting'] = 'amount'
        context.user_data['step'] = 'withdraw'
        context.user_data['player_id'] = account['player_id']
        context.user_data['available_balance'] = balance
    
    elif query.data == 'my_account':
        account = db.get_ichancy_account(user_id)
        if not account:
            await query.edit_message_text("❗ لديك 0 حسابات ايتشانسي")
            return
        
        # جلب الرصيد الحالي
        result = api.get_player_balance(account['player_id'])
        balance = result['balance'] if result['success'] else "غير متاح"
        
        message = f"""
📋 *معلومات حسابك:*

👤 *اسم الدخول:* `{account['login']}`
📧 *الإيميل:* `{account['email']}`
🔑 *كلمة المرور:* `{account['password']}`
🆔 *رقم اللاعب:* `{account['player_id']}`
📅 *تاريخ الإنشاء:* `{account['created_at']}`
💰 *الرصيد الحالي:* `{balance}` NSP
        """
        
        await query.edit_message_text(message, parse_mode='Markdown')
    
    elif query.data == 'my_balance':
        user_balance = db.get_user_balance(user_id)
        await query.edit_message_text(
            f"💰 *رصيدك المحلي:* {user_balance} NSP",
            parse_mode='Markdown'
        )
    
    elif query.data == 'site_url':
        await query.edit_message_text(
            "🌐 *رابط موقع Ichancy:*\n"
            "https://ichancy.com\n\n"
            "🔗 *لوحة الوكيل:*\n"
            "https://agents.ichancy.com",
            parse_mode='Markdown'
        )
    
    elif query.data == 'help':
        await help_command(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    user_id = str(update.effective_user.id)
    chat_id = update.message.chat.id
    text = update.message.text.strip()
    
    if 'awaiting' not in context.user_data:
        await update.message.reply_text("الرجاء استخدام الأزرار للتفاعل مع البوت")
        return
    
    awaiting = context.user_data['awaiting']
    step = context.user_data.get('step', '')
    
    try:
        if step == 'create_account':
            if awaiting == 'username':
                if not re.match(r'^[A-Za-z0-9_.-]+$', text):
                    await update.message.reply_text(
                        "❌ يجب استخدام الأحرف اللاتينية والأرقام فقط!\n"
                        "أعد إدخال اسم المستخدم:"
                    )
                    return
                
                base_login = f"{text}_TSA"
                existing_logins = db.get_all_ichancy_logins()
                
                # التحقق من توفر الاسم
                if base_login in existing_logins or api.check_player_exists(base_login):
                    counter = 1
                    new_login = f"{base_login}{counter}"
                    while new_login in existing_logins or api.check_player_exists(new_login):
                        counter += 1
                        new_login = f"{base_login}{counter}"
                        if counter > 10:
                            rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=2))
                            new_login = f"{base_login}{rand_str}"
                            break
                    base_login = new_login
                
                context.user_data['login'] = base_login
                context.user_data['awaiting'] = 'password'
                
                await update.message.reply_text(
                    "✅ تم حفظ اسم المستخدم\n"
                    "أدخل كلمة المرور (يجب أن تكون بين 8 إلى 11 حرفاً):"
                )
            
            elif awaiting == 'password':
                if len(text) < 8 or len(text) > 11:
                    await update.message.reply_text(
                        "❌ كلمة المرور يجب أن تكون بين 8 إلى 11 حرفاً!\n"
                        "أعد إدخال كلمة المرور:"
                    )
                    return
                
                context.user_data['password'] = text
                context.user_data['awaiting'] = 'initial_amount'
                
                await update.message.reply_text(
                    "✅ تم حفظ كلمة المرور\n"
                    "أدخل مبلغ الشحن الابتدائي (الحد الأدنى 10 NSP):"
                )
            
            elif awaiting == 'initial_amount':
                try:
                    amount = int(text)
                    if amount < 10:
                        await update.message.reply_text(
                            "❌ الحد الأدنى للإيداع هو 10 NSP!\n"
                            "أعد إدخال المبلغ:"
                        )
                        return
                    
                    await create_account_process(update, context, amount)
                    
                except ValueError:
                    await update.message.reply_text(
                        "❌ يرجى إدخال رقم صحيح!\n"
                        "أعد إدخال المبلغ:"
                    )
        
        elif step in ['deposit', 'withdraw']:
            if awaiting == 'amount':
                try:
                    amount = int(text)
                    if amount < 10:
                        await update.message.reply_text(
                            "❌ الحد الأدنى هو 10 NSP!\n"
                            "أعد إدخال المبلغ:"
                        )
                        return
                    
                    player_id = context.user_data['player_id']
                    
                    if step == 'deposit':
                        await deposit_process(update, user_id, player_id, amount)
                    else:
                        available = context.user_data.get('available_balance', 0)
                        if amount > available:
                            await update.message.reply_text(
                                f"❌ الرصيد غير كافي!\n"
                                f"الرصيد المتاح: {available} NSP\n"
                                "أعد إدخال المبلغ:"
                            )
                            return
                        
                        await withdraw_process(update, user_id, player_id, amount)
                    
                    # تنظيف البيانات
                    if chat_id in active_users:
                        active_users.discard(chat_id)
                    context.user_data.clear()
                    
                except ValueError:
                    await update.message.reply_text(
                        "❌ يرجى إدخال رقم صحيح!\n"
                        "أعد إدخال المبلغ:"
                    )
    
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
        
        # تنظيف في حالة الخطأ
        if chat_id in active_users:
            active_users.discard(chat_id)
        context.user_data.clear()

async def create_account_process(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
    """عملية إنشاء الحساب"""
    user_id = str(update.effective_user.id)
    login = context.user_data['login']
    password = context.user_data['password']
    
    try:
        await update.message.reply_text("⏳ جاري إنشاء الحساب...")
        
        result = api.create_player_with_credentials(login, password)
        
        if not result.get('success', False):
            error_msg = result.get('error', 'فشل غير معروف')
            await update.message.reply_text(f"❌ فشل إنشاء الحساب: {error_msg}")
            return
        
        player_id = result.get('player_id')
        email = result.get('email', f"{login}@TSA.com")
        
        # حفظ في قاعدة البيانات
        success = db.add_ichancy_account(
            user_id=user_id,
            player_id=player_id,
            login=login,
            password=password,
            email=email,
            initial_balance=amount
        )
        
        if not success:
            await update.message.reply_text("❌ فشل حفظ الحساب في قاعدة البيانات")
            return
        
        # إذا كان هناك مبلغ ابتدائي
        if amount > 0:
            await update.message.reply_text(f"⏳ جاري شحن {amount} NSP...")
            deposit_result = api.deposit_to_player(player_id, amount)
            
            if not deposit_result.get('success', False):
                error_msg = deposit_result.get('error', 'فشل الشحن')
                await update.message.reply_text(
                    f"⚠️ تم إنشاء الحساب ولكن فشل الشحن:\n{error_msg}"
                )
            else:
                # خصم من رصيد المستخدم المحلي
                db.update_user_balance(user_id, amount, "subtract")
        
        # جلب الرصيد النهائي
        balance_result = api.get_player_balance(player_id)
        final_balance = balance_result.get('balance', amount) if balance_result.get('success', False) else amount
        
        # رسالة النجاح
        success_message = f"""
✅ *تم إنشاء الحساب بنجاح!*

👤 *اسم المستخدم:* `{login}`
📧 *الإيميل:* `{email}`
🔑 *كلمة المرور:* `{password}`
🆔 *رقم اللاعب:* `{player_id}`
💰 *الرصيد الابتدائي:* {amount} NSP
📊 *الرصيد الحالي:* {final_balance} NSP

⚠️ *احفظ هذه البيانات في مكان آمن!*
        """
        
        await update.message.reply_text(success_message, parse_mode='Markdown')
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error in create_account_process: {e}")
        await update.message.reply_text(f"❌ حدث خطأ أثناء إنشاء الحساب: {str(e)}")

async def deposit_process(update: Update, user_id: str, player_id: str, amount: float):
    """عملية الإيداع"""
    try:
        await update.message.reply_text(f"⏳ جاري إيداع {amount} NSP...")
        
        # التحقق من رصيد المستخدم المحلي
        user_balance = db.get_user_balance(user_id)
        if user_balance < amount:
            await update.message.reply_text(
                f"❌ رصيدك غير كافي!\n"
                f"رصيدك الحالي: {user_balance} NSP"
            )
            return
        
        # تنفيذ الإيداع عبر API
        result = api.deposit_to_player(player_id, amount)
        
        if result.get('success', False):
            # خصم من رصيد المستخدم المحلي
            db.update_user_balance(user_id, amount, "subtract")
            await update.message.reply_text(f"✅ تم إيداع {amount} NSP بنجاح!")
        else:
            error_msg = result.get('error', 'فشل الإيداع')
            await update.message.reply_text(f"❌ فشل الإيداع: {error_msg}")
            
    except Exception as e:
        logger.error(f"Error in deposit_process: {e}")
        await update.message.reply_text(f"❌ حدث خطأ أثناء الإيداع: {str(e)}")

async def withdraw_process(update: Update, user_id: str, player_id: str, amount: float):
    """عملية السحب"""
    try:
        await update.message.reply_text(f"⏳ جاري سحب {amount} NSP...")
        
        # تنفيذ السحب عبر API
        result = api.withdraw_from_player(player_id, amount)
        
        if result.get('success', False):
            # إضافة إلى رصيد المستخدم المحلي
            db.update_user_balance(user_id, amount, "add")
            await update.message.reply_text(f"✅ تم سحب {amount} NSP بنجاح!")
        else:
            error_msg = result.get('error', 'فشل السحب')
            await update.message.reply_text(f"❌ فشل السحب: {error_msg}")
            
    except Exception as e:
        logger.error(f"Error in withdraw_process: {e}")
        await update.message.reply_text(f"❌ حدث خطأ أثناء السحب: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأخطاء"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ حدث خطأ غير متوقع!\n"
                "يرجى المحاولة مرة أخرى لاحقاً."
            )
        except:
            pass

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    logger.info("🚀 Starting Ichancy Bot...")
    logger.info(f"Bot Token: {'✓' if BOT_TOKEN else '✗'}")
    logger.info(f"Agent Username: {'✓' if AGENT_USERNAME else '✗'}")
    logger.info(f"Agent Password: {'✓' if AGENT_PASSWORD else '✗'}")
    logger.info(f"Parent ID: {'✓' if PARENT_ID else '✗'}")
    
    # إنشاء تطبيق البوت
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("✅ Bot handlers registered successfully")
    logger.info("🤖 Bot is starting...")
    
    # تشغيل البوت
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
