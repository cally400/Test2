import os
import logging
import asyncio
import pickle
import random
import string
import re
import cloudscraper
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
import sqlite3

# ========== تهيئة الإعدادات ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== إعدادات API ichancy ==========
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "tsa_robert@tsa.com")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "K041@051kkk")
PARENT_ID = os.getenv("PARENT_ID", "2307909")

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

# ========== حالات المحادثة ==========
USERNAME, PASSWORD, INITIAL_AMOUNT = range(3)

# ========== قاعدة البيانات ==========
class Database:
    def __init__(self, db_path="ichancy_bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
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
                created_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
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
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    
    def update_user_balance(self, user_id: str, amount: float, operation: str = "add"):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False
        
        current_balance = result[0]
        if operation == "add":
            new_balance = current_balance + amount
        elif operation == "subtract":
            if current_balance < amount:
                conn.close()
                return False
            new_balance = current_balance - amount
        else:
            new_balance = amount
        
        cursor.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (new_balance, user_id)
        )
        conn.commit()
        conn.close()
        return True
    
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
        cursor.execute(
            "SELECT * FROM ichancy_accounts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        
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
    
    def get_all_ichancy_logins(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT login FROM ichancy_accounts WHERE login IS NOT NULL")
        results = cursor.fetchall()
        conn.close()
        return [r[0] for r in results] if results else []
    
    def add_transaction(self, user_id: str, player_id: str, 
                       trans_type: str, amount: float, status: str, details: str = ""):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions 
            (user_id, player_id, type, amount, status, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, player_id, trans_type, amount, status, details))
        conn.commit()
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
        """إنشاء حساب جديد"""
        email = f"{login}@TSA.com"
        
        # تحقق من تفرد الإيميل
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
        
        resp = self.scraper.post(DEPOSIT_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        return {
            "success": data.get("result", False),
            "status": resp.status_code,
            "data": data
        }
    
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
        
        resp = self.scraper.post(WITHDRAW_URL, json=payload, headers=headers, timeout=30)
        data = resp.json()
        
        return {
            "success": data.get("result", False),
            "status": resp.status_code,
            "data": data
        }
    
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
class IchancyBot:
    def __init__(self, token: str):
        self.token = token
        self.api = IchancyAPI()
        self.db = Database()
        self.active_users = set()
        
        # إنشاء تطبيق التليجرام
        self.application = Application.builder().token(token).build()
        
        # إضافة handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        # تعريف أوامر البوت
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("balance", self.balance_command))
        
        # معالجة الأزرار
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # معالجة الرسائل النصية
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # معالجة الأخطاء
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بدء البوت"""
        user_id = str(update.effective_user.id)
        username = update.effective_user.username
        
        # إضافة المستخدم إلى قاعدة البيانات
        self.db.add_user(user_id, username)
        
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
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض رصيد المستخدم"""
        user_id = str(update.effective_user.id)
        balance = self.db.get_user_balance(user_id)
        
        await update.message.reply_text(
            f"💰 *رصيدك الحالي:* {balance} NSP",
            parse_mode='Markdown'
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأزرار"""
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        chat_id = query.message.chat.id
        
        if query.data == 'create_account':
            # التحقق من وجود حساب بالفعل
            existing = self.db.get_ichancy_account(user_id)
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
            account = self.db.get_ichancy_account(user_id)
            if not account:
                await query.edit_message_text("❗ لم تنشئ حساباً بعد!")
                return
            
            if chat_id in self.active_users:
                await query.edit_message_text("⏳ يرجى الانتظار قبل المحاولة مرة أخرى")
                return
            
            self.active_users.add(chat_id)
            await query.edit_message_text(
                f"💳 *الحساب:* `{account['login']}`\n"
                "أدخل مبلغ الإيداع (الحد الأدنى 10 NSP):",
                parse_mode='Markdown'
            )
            context.user_data['awaiting'] = 'amount'
            context.user_data['step'] = 'deposit'
            context.user_data['player_id'] = account['player_id']
        
        elif query.data == 'withdraw':
            account = self.db.get_ichancy_account(user_id)
            if not account:
                await query.edit_message_text("❗ لم تنشئ حساباً بعد!")
                return
            
            if chat_id in self.active_users:
                await query.edit_message_text("⏳ يرجى الانتظار قبل المحاولة مرة أخرى")
                return
            
            self.active_users.add(chat_id)
            
            # جلب الرصيد أولاً
            result = self.api.get_player_balance(account['player_id'])
            if not result['success']:
                await query.edit_message_text("❌ تعذر جلب الرصيد من الموقع")
                self.active_users.discard(chat_id)
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
            account = self.db.get_ichancy_account(user_id)
            if not account:
                await query.edit_message_text("❗ لديك 0 حسابات ايتشانسي")
                return
            
            # جلب الرصيد الحالي
            result = self.api.get_player_balance(account['player_id'])
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
            user_balance = self.db.get_user_balance(user_id)
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
            await self.help_command(update, context)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية"""
        user_id = str(update.effective_user.id)
        chat_id = update.message.chat.id
        text = update.message.text.strip()
        
        # تحقق من وجود عملية جارية
        if 'awaiting' not in context.user_data:
            await update.message.reply_text("الرجاء استخدام الأزرار للتفاعل مع البوت")
            return
        
        awaiting = context.user_data['awaiting']
        step = context.user_data.get('step', '')
        
        try:
            if step == 'create_account':
                if awaiting == 'username':
                    # التحقق من اسم المستخدم
                    if not re.match(r'^[A-Za-z0-9_.-]+$', text):
                        await update.message.reply_text(
                            "❌ يجب استخدام الأحرف اللاتينية والأرقام فقط!\n"
                            "أعد إدخال اسم المستخدم:"
                        )
                        return
                    
                    # إضافة لاحقة TSA
                    base_login = f"{text}_TSA"
                    
                    # التحقق من تفرد الاسم
                    existing_logins = self.db.get_all_ichancy_logins()
                    if base_login in existing_logins or self.api.check_player_exists(base_login):
                        # محاولة أسماء بديلة
                        counter = 1
                        new_login = f"{base_login}{counter}"
                        while new_login in existing_logins or self.api.check_player_exists(new_login):
                            counter += 1
                            new_login = f"{base_login}{counter}"
                            if counter > 10:
                                # إنشاء اسم عشوائي
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
                    # التحقق من طول كلمة المرور
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
                        
                        # بدء عملية الإنشاء
                        await self.create_account_process(update, context, amount)
                        
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
                            await self.deposit_process(update, user_id, player_id, amount)
                        else:
                            # التحقق من الرصيد المتاح للسحب
                            available = context.user_data.get('available_balance', 0)
                            if amount > available:
                                await update.message.reply_text(
                                    f"❌ الرصيد غير كافي!\n"
                                    f"الرصيد المتاح: {available} NSP\n"
                                    "أعد إدخال المبلغ:"
                                )
                                return
                            
                            await self.withdraw_process(update, user_id, player_id, amount)
                        
                        # تنظيف البيانات
                        if chat_id in self.active_users:
                            self.active_users.discard(chat_id)
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
            if chat_id in self.active_users:
                self.active_users.discard(chat_id)
            context.user_data.clear()
    
    async def create_account_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
        """عملية إنشاء الحساب"""
        user_id = str(update.effective_user.id)
        chat_id = update.message.chat.id
        
        login = context.user_data['login']
        password = context.user_data['password']
        
        try:
            await update.message.reply_text("⏳ جاري إنشاء الحساب...")
            
            # إنشاء الحساب عبر API
            result = self.api.create_player_with_credentials(login, password)
            
            if not result['success']:
                await update.message.reply_text(f"❌ فشل إنشاء الحساب: {result['error']}")
                return
            
            player_id = result['player_id']
            email = result['email']
            
            # حفظ في قاعدة البيانات
            self.db.add_ichancy_account(
                user_id=user_id,
                player_id=player_id,
                login=login,
                password=password,
                email=email,
                initial_balance=amount
            )
            
            # إذا كان هناك مبلغ ابتدائي
            if amount > 0:
                await update.message.reply_text(f"⏳ جاري شحن {amount} NSP...")
                deposit_result = self.api.deposit_to_player(player_id, amount)
                
                if not deposit_result['success']:
                    # الحساب أنشئ ولكن الشحن فشل
                    error_msg = deposit_result['data'].get('notification', [{}])[0].get('content', 'فشل الشحن')
                    await update.message.reply_text(
                        f"⚠️ تم إنشاء الحساب ولكن فشل الشحن:\n{error_msg}"
                    )
                else:
                    # خصم من رصيد المستخدم
                    self.db.update_user_balance(user_id, amount, "subtract")
                    self.db.add_transaction(
                        user_id, player_id, "deposit", amount, 
                        "success", "شحن ابتدائي عند الإنشاء"
                    )
            
            # جلب الرصيد النهائي
            balance_result = self.api.get_player_balance(player_id)
            final_balance = balance_result['balance'] if balance_result['success'] else amount
            
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
            
            # تنظيف البيانات
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error in create_account_process: {e}")
            await update.message.reply_text(f"❌ حدث خطأ أثناء إنشاء الحساب: {str(e)}")
    
    async def deposit_process(self, update: Update, user_id: str, player_id: str, amount: float):
        """عملية الإيداع"""
        try:
            await update.message.reply_text(f"⏳ جاري إيداع {amount} NSP...")
            
            # التحقق من رصيد المستخدم المحلي
            user_balance = self.db.get_user_balance(user_id)
            if user_balance < amount:
                await update.message.reply_text(
                    f"❌ رصيدك غير كافي!\n"
                    f"رصيدك الحالي: {user_balance} NSP"
                )
                return
            
            # تنفيذ الإيداع عبر API
            result = self.api.deposit_to_player(player_id, amount)
            
            if result['success']:
                # خصم من رصيد المستخدم
                self.db.update_user_balance(user_id, amount, "subtract")
                self.db.add_transaction(
                    user_id, player_id, "deposit", amount, "success", "إيداع رصيد"
                )
                
                await update.message.reply_text(f"✅ تم إيداع {amount} NSP بنجاح!")
            else:
                error_msg = result['data'].get('notification', [{}])[0].get('content', 'فشل الإيداع')
                await update.message.reply_text(f"❌ فشل الإيداع: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error in deposit_process: {e}")
            await update.message.reply_text(f"❌ حدث خطأ أثناء الإيداع: {str(e)}")
    
    async def withdraw_process(self, update: Update, user_id: str, player_id: str, amount: float):
        """عملية السحب"""
        try:
            await update.message.reply_text(f"⏳ جاري سحب {amount} NSP...")
            
            # تنفيذ السحب عبر API
            result = self.api.withdraw_from_player(player_id, amount)
            
            if result['success']:
                # إضافة إلى رصيد المستخدم
                self.db.update_user_balance(user_id, amount, "add")
                self.db.add_transaction(
                    user_id, player_id, "withdraw", amount, "success", "سحب رصيد"
                )
                
                await update.message.reply_text(f"✅ تم سحب {amount} NSP بنجاح!")
            else:
                error_msg = result['data'].get('notification', [{}])[0].get('content', 'فشل السحب')
                await update.message.reply_text(f"❌ فشل السحب: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error in withdraw_process: {e}")
            await update.message.reply_text(f"❌ حدث خطأ أثناء السحب: {str(e)}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    def run(self):
        """تشغيل البوت"""
        logger.info("Starting Ichancy Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# ========== التشغيل الرئيسي ==========
def main():
    # أدخل توكن البوت هنا
    TOKEN = "8102146925:AAE73uGcF7a4YZ_vrP1fXvXzUve3Wiu3MwQ"  # استبدل هذا بتوكن البوت الخاص بك
    
    # إذا كان التوكن في متغير بيئي
    if "BOT_TOKEN" in os.environ:
        TOKEN = os.environ["BOT_TOKEN"]
    
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ الرجاء إدخال توكن البوت!")
        print("\nخطوات الحصول على التوكن:")
        print("1. افتح @BotFather في تليجرام")
        print("2. أرسل /newbot")
        print("3. اتبع التعليمات لإنشاء بوت جديد")
        print("4. انسخ التوكن (سيبدو هكذا: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz)")
        print("\nيمكنك تعيين التوكن بعدة طرق:")
        print("1. تعديل المتغير TOKEN في الكود مباشرة")
        print("2. استخدام متغير بيئي: export BOT_TOKEN='your_token_here'")
        print("3. استخدام ملف .env: BOT_TOKEN=your_token_here")
        return
    
    try:
        bot = IchancyBot(TOKEN)
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == "__main__":
    main()
