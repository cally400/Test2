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
AGENT_USERNAME = os.getenv("AGENT_USERNAME")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD")
PARENT_ID = os.getenv("PARENT_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# قيم افتراضية للتنمية المحلية
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not all([AGENT_USERNAME, AGENT_PASSWORD, PARENT_ID, BOT_TOKEN]):
    logger.error("❌ Missing required environment variables!")
    logger.error("Required: AGENT_USERNAME, AGENT_PASSWORD, PARENT_ID, BOT_TOKEN")
    exit(1)

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
        self.db_path = os.getenv("DATABASE_URL", "sqlite:///ichancy_bot.db")
        self.init_db()
    
    def get_connection(self):
        if self.db_path.startswith("sqlite"):
            # استخراج مسار SQLite من السلسلة
            path = self.db_path.replace("sqlite:///", "")
            return sqlite3.connect(path)
        else:
            # لـ PostgreSQL أو MySQL
            import psycopg2
            return psycopg2.connect(self.db_path)
    
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
                    id SERIAL PRIMARY KEY,
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
                    id SERIAL PRIMARY KEY,
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
                "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
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
            cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
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
            cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
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
                "UPDATE users SET balance = %s WHERE user_id = %s",
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
                VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                "SELECT * FROM ichancy_accounts WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
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
    
    def login_to_agent(self):
        payload = {"username": AGENT_USERNAME, "password": AGENT_PASSWORD}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        try:
            resp = self.scraper.post(SIGNIN_URL, json=payload, headers=headers, timeout=30)
            data = resp.json()
            
            if data.get("result", False):
                self.save_cookies()
                self.is_logged_in = True
                return True, data
            return False, data
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False, {"error": str(e)}
    
    def ensure_login(self):
        if not self.is_logged_in:
            success, data = self.login_to_agent()
            if not success:
                raise Exception(f"فشل تسجيل الدخول: {data}")
    
    def with_retry(func):
        def wrapper(self, *args, **kwargs):
            try:
                self.ensure_login()
                return func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"API error in {func.__name__}: {e}")
                self.is_logged_in = False
                self.ensure_login()
                return func(self, *args, **kwargs)
        return wrapper
    
    @with_retry
    def create_player_with_credentials(self, login: str, password: str):
        email = f"{login}@TSA.com"
        
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
        
        resp = self.scraper.post(CREATE_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        if data.get("result", False):
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
            return {
                "success": False,
                "error": data.get("notification", [{}])[0].get("content", "فشل إنشاء الحساب")
            }
    
    def get_player_id_by_login(self, login: str):
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        resp = self.scraper.post(STATISTICS_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        records = data.get("result", {}).get("records", [])
        for record in records:
            if record.get("username") == login:
                return record.get("playerId")
        return None
    
    @with_retry
    def deposit_to_player(self, player_id: str, amount: float):
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
        
        resp = self.scraper.post(DEPOSIT_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        return {
            "success": data.get("result", False),
            "status": resp.status_code,
            "data": data
        }
    
    @with_retry
    def withdraw_from_player(self, player_id: str, amount: float):
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
        
        resp = self.scraper.post(WITHDRAW_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        return {
            "success": data.get("result", False),
            "status": resp.status_code,
            "data": data
        }
    
    @with_retry
    def get_player_balance(self, player_id: str):
        payload = {"playerId": str(player_id)}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        resp = self.scraper.post(GET_BALANCE_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        results = data.get("result", [])
        balance = results[0].get("balance", 0) if isinstance(results, list) and results else 0
        
        return {
            "success": True,
            "balance": balance,
            "status": resp.status_code,
            "data": data
        }
    
    def check_email_exists(self, email: str):
        payload = {"page": 1, "pageSize": 100, "filter": {"email": email}}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        resp = self.scraper.post(STATISTICS_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        records = data.get("result", {}).get("records", [])
        for record in records:
            if record.get("email") == email:
                return True
        return False
    
    def check_player_exists(self, login: str):
        payload = {"page": 1, "pageSize": 100, "filter": {"login": login}}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": ORIGIN,
            "Referer": REFERER
        }
        
        resp = self.scraper.post(STATISTICS_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        records = data.get("result", {}).get("records", [])
        for record in records:
            if record.get("username") == login:
                return True
        return False

# ========== Telegram Bot ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت"""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username
    
    # إضافة المستخدم إلى قاعدة البيانات
    db = Database()
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
    db = Database()
    balance = db.get_user_balance(user_id)
    
    await update.message.reply_text(
        f"💰 *رصيدك الحالي:* {balance} NSP",
        parse_mode='Markdown'
    )

# المتغيرات العامة
active_users = set()
api = IchancyAPI()
db = Database()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار"""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    chat_id = query.message.chat.id
    
    if query.data == 'create_account':
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
        
        if chat_id in active_users:
            active_users.discard(chat_id)
        context.user_data.clear()

async def create_account_process(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
    user_id = str(update.effective_user.id)
    login = context.user_data['login']
    password = context.user_data['password']
    
    try:
        await update.message.reply_text("⏳ جاري إنشاء الحساب...")
        
        result = api.create_player_with_credentials(login, password)
        
        if not result['success']:
            await update.message.reply_text(f"❌ فشل إنشاء الحساب: {result['error']}")
            return
        
        player_id = result['player_id']
        email = result['email']
        
        db.add_ichancy_account(
            user_id=user_id,
            player_id=player_id,
            login=login,
            password=password,
            email=email,
            initial_balance=amount
        )
        
        if amount > 0:
            await update.message.reply_text(f"⏳ جاري شحن {amount} NSP...")
            deposit_result = api.deposit_to_player(player_id, amount)
            
            if not deposit_result['success']:
                error_msg = deposit_result['data'].get('notification', [{}])[0].get('content', 'فشل الشحن')
                await update.message.reply_text(
                    f"⚠️ تم إنشاء الحساب ولكن فشل الشحن:\n{error_msg}"
                )
            else:
                db.update_user_balance(user_id, amount, "subtract")
        
        balance_result = api.get_player_balance(player_id)
        final_balance = balance_result['balance'] if balance_result['success'] else amount
        
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
    try:
        await update.message.reply_text(f"⏳ جاري إيداع {amount} NSP...")
        
        user_balance = db.get_user_balance(user_id)
        if user_balance < amount:
            await update.message.reply_text(
                f"❌ رصيدك غير كافي!\n"
                f"رصيدك الحالي: {user_balance} NSP"
            )
            return
        
        result = api.deposit_to_player(player_id, amount)
        
        if result['success']:
            db.update_user_balance(user_id, amount, "subtract")
            await update.message.reply_text(f"✅ تم إيداع {amount} NSP بنجاح!")
        else:
            error_msg = result['data'].get('notification', [{}])[0].get('content', 'فشل الإيداع')
            await update.message.reply_text(f"❌ فشل الإيداع: {error_msg}")
            
    except Exception as e:
        logger.error(f"Error in deposit_process: {e}")
        await update.message.reply_text(f"❌ حدث خطأ أثناء الإيداع: {str(e)}")

async def withdraw_process(update: Update, user_id: str, player_id: str, amount: float):
    try:
        await update.message.reply_text(f"⏳ جاري سحب {amount} NSP...")
        
        result = api.withdraw_from_player(player_id, amount)
        
        if result['success']:
            db.update_user_balance(user_id, amount, "add")
            await update.message.reply_text(f"✅ تم سحب {amount} NSP بنجاح!")
        else:
            error_msg = result['data'].get('notification', [{}])[0].get('content', 'فشل السحب')
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
    
    # التحقق من المتغيرات البيئية
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found in environment variables!")
        logger.error("Please set BOT_TOKEN environment variable")
        exit(1)
    
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
