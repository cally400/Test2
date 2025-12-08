# database.py
import os
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import psycopg2
from psycopg2.extras import RealDictCursor, DictCursor
import sqlite3
from contextlib import contextmanager
from config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """مدير قاعدة البيانات المتوافق مع Railway"""
    
    def __init__(self):
        self.db_type = "postgresql" if config.DATABASE_URL else "sqlite"
        self.init_database()
        logger.info(f"✅ Database initialized: {self.db_type}")
    
    @contextmanager
    def get_connection(self):
        """الحصول على اتصال قاعدة البيانات"""
        if self.db_type == "postgresql":
            conn = psycopg2.connect(
                config.DATABASE_URL,
                cursor_factory=RealDictCursor
            )
            try:
                yield conn
            finally:
                conn.close()
        else:
            conn = sqlite3.connect("ichancy_bot.db")
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
    
    @contextmanager
    def get_cursor(self, conn):
        """الحصول على مؤشر قاعدة البيانات"""
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def init_database(self):
        """تهيئة جداول قاعدة البيانات"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    
                    if self.db_type == "postgresql":
                        # جدول المستخدمين (PostgreSQL)
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS users (
                                user_id VARCHAR(50) PRIMARY KEY,
                                username VARCHAR(100),
                                balance DECIMAL(10, 2) DEFAULT 0,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                last_active TIMESTAMP,
                                is_admin BOOLEAN DEFAULT FALSE,
                                language VARCHAR(10) DEFAULT 'ar'
                            )
                        ''')
                        
                        # جدول حسابات Ichancy
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS ichancy_accounts (
                                id SERIAL PRIMARY KEY,
                                user_id VARCHAR(50) REFERENCES users(user_id) ON DELETE CASCADE,
                                player_id VARCHAR(50),
                                login VARCHAR(100) UNIQUE,
                                password VARCHAR(100),
                                email VARCHAR(150),
                                initial_balance DECIMAL(10, 2) DEFAULT 0,
                                current_balance DECIMAL(10, 2) DEFAULT 0,
                                status VARCHAR(20) DEFAULT 'active',
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        ''')
                        
                        # جدول المعاملات
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS transactions (
                                id SERIAL PRIMARY KEY,
                                user_id VARCHAR(50) REFERENCES users(user_id) ON DELETE CASCADE,
                                player_id VARCHAR(50),
                                transaction_type VARCHAR(20),
                                amount DECIMAL(10, 2),
                                currency VARCHAR(10) DEFAULT 'NSP',
                                status VARCHAR(50),
                                details TEXT,
                                error_message TEXT,
                                reference_id VARCHAR(100),
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        ''')
                        
                        # جدول سجلات الأخطاء
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS error_logs (
                                id SERIAL PRIMARY KEY,
                                user_id VARCHAR(50),
                                error_type VARCHAR(50),
                                error_message TEXT,
                                stack_trace TEXT,
                                api_endpoint VARCHAR(200),
                                request_data TEXT,
                                response_data TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        ''')
                        
                        # فهارس للأداء
                        cursor.execute('''
                            CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)
                        ''')
                        cursor.execute('''
                            CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON ichancy_accounts(user_id)
                        ''')
                        cursor.execute('''
                            CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)
                        ''')
                        cursor.execute('''
                            CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at)
                        ''')
                        
                    else:
                        # SQLite implementation
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS users (
                                user_id TEXT PRIMARY KEY,
                                username TEXT,
                                balance REAL DEFAULT 0,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                last_active TIMESTAMP,
                                is_admin BOOLEAN DEFAULT 0,
                                language TEXT DEFAULT 'ar'
                            )
                        ''')
                        
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS ichancy_accounts (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id TEXT,
                                player_id TEXT,
                                login TEXT UNIQUE,
                                password TEXT,
                                email TEXT,
                                initial_balance REAL DEFAULT 0,
                                current_balance REAL DEFAULT 0,
                                status TEXT DEFAULT 'active',
                                created_at TIMESTAMP,
                                updated_at TIMESTAMP,
                                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                            )
                        ''')
                        
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS transactions (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id TEXT,
                                player_id TEXT,
                                transaction_type TEXT,
                                amount REAL,
                                currency TEXT DEFAULT 'NSP',
                                status TEXT,
                                details TEXT,
                                error_message TEXT,
                                reference_id TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                            )
                        ''')
                        
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS error_logs (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id TEXT,
                                error_type TEXT,
                                error_message TEXT,
                                stack_trace TEXT,
                                api_endpoint TEXT,
                                request_data TEXT,
                                response_data TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        ''')
                    
                    logger.info("✅ Database tables created successfully")
        
        except Exception as e:
            logger.error(f"❌ فشل تهيئة قاعدة البيانات: {str(e)}")
            raise Exception(f"فشل تهيئة قاعدة البيانات: {str(e)}")
    
    # ========== إدارة المستخدمين ==========
    def add_user(self, user_id: str, username: str = None) -> bool:
        """إضافة مستخدم جديد"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            INSERT INTO users (user_id, username, last_active, is_admin)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (user_id) DO UPDATE SET
                                username = EXCLUDED.username,
                                last_active = EXCLUDED.last_active
                        ''', (user_id, username, datetime.now(), user_id in config.ADMIN_USER_IDS))
                    else:
                        cursor.execute('''
                            INSERT OR REPLACE INTO users (user_id, username, last_active, is_admin)
                            VALUES (?, ?, ?, ?)
                        ''', (user_id, username, datetime.now(), 1 if user_id in config.ADMIN_USER_IDS else 0))
                    
                    logger.info(f"✅ تم إضافة/تحديث المستخدم: {user_id}")
                    return True
        
        except Exception as e:
            logger.error(f"❌ فشل إضافة المستخدم {user_id}: {str(e)}")
            return False
    
    def update_user_activity(self, user_id: str) -> bool:
        """تحديث آخر نشاط للمستخدم"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute(
                            "UPDATE users SET last_active = %s WHERE user_id = %s",
                            (datetime.now(), user_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE users SET last_active = ? WHERE user_id = ?",
                            (datetime.now(), user_id)
                        )
                    
                    return cursor.rowcount > 0
        
        except Exception as e:
            logger.error(f"❌ فشل تحديث نشاط المستخدم {user_id}: {str(e)}")
            return False
    
    def get_user_balance(self, user_id: str) -> float:
        """الحصول على رصيد المستخدم"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute(
                            "SELECT balance FROM users WHERE user_id = %s",
                            (user_id,)
                        )
                    else:
                        cursor.execute(
                            "SELECT balance FROM users WHERE user_id = ?",
                            (user_id,)
                        )
                    
                    result = cursor.fetchone()
                    return float(result['balance']) if result else 0.0
        
        except Exception as e:
            logger.error(f"❌ فشل جلب رصيد المستخدم {user_id}: {str(e)}")
            return 0.0
    
    def update_user_balance(self, user_id: str, amount: float, operation: str = "add") -> bool:
        """تحديث رصيد المستخدم مع تسجيل الخطأ"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    
                    # جلب الرصيد الحالي
                    if self.db_type == "postgresql":
                        cursor.execute(
                            "SELECT balance FROM users WHERE user_id = %s FOR UPDATE",
                            (user_id,)
                        )
                    else:
                        cursor.execute(
                            "SELECT balance FROM users WHERE user_id = ?",
                            (user_id,)
                        )
                    
                    result = cursor.fetchone()
                    if not result:
                        raise Exception(f"المستخدم {user_id} غير موجود")
                    
                    current_balance = float(result['balance'])
                    
                    # حساب الرصيد الجديد
                    if operation == "add":
                        new_balance = current_balance + amount
                    elif operation == "subtract":
                        if current_balance < amount:
                            raise Exception(f"رصيد غير كافي. الرصيد الحالي: {current_balance}، المطلوب: {amount}")
                        new_balance = current_balance - amount
                    elif operation == "set":
                        new_balance = amount
                    else:
                        raise Exception(f"عملية غير صالحة: {operation}")
                    
                    # تحديث الرصيد
                    if self.db_type == "postgresql":
                        cursor.execute(
                            "UPDATE users SET balance = %s WHERE user_id = %s",
                            (new_balance, user_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE users SET balance = ? WHERE user_id = ?",
                            (new_balance, user_id)
                        )
                    
                    logger.info(f"✅ تم تحديث رصيد المستخدم {user_id}: {current_balance} → {new_balance}")
                    return True
        
        except Exception as e:
            error_msg = f"❌ فشل تحديث رصيد المستخدم {user_id}: {str(e)}"
            logger.error(error_msg)
            self.log_error(
                user_id=user_id,
                error_type="update_balance_failed",
                error_message=error_msg,
                api_endpoint="database.update_user_balance"
            )
            return False
    
    # ========== إدارة حسابات Ichancy ==========
    def add_ichancy_account(self, account_data: Dict) -> bool:
        """إضافة حساب Ichancy جديد"""
        try:
            required_fields = ['user_id', 'player_id', 'login', 'password', 'email']
            for field in required_fields:
                if field not in account_data:
                    raise Exception(f"الحقل المطلوب {field} مفقود")
            
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            INSERT INTO ichancy_accounts 
                            (user_id, player_id, login, password, email, initial_balance, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            account_data['user_id'],
                            account_data['player_id'],
                            account_data['login'],
                            account_data['password'],
                            account_data['email'],
                            account_data.get('initial_balance', 0),
                            datetime.now(),
                            datetime.now()
                        ))
                    else:
                        cursor.execute('''
                            INSERT INTO ichancy_accounts 
                            (user_id, player_id, login, password, email, initial_balance, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            account_data['user_id'],
                            account_data['player_id'],
                            account_data['login'],
                            account_data['password'],
                            account_data['email'],
                            account_data.get('initial_balance', 0),
                            datetime.now(),
                            datetime.now()
                        ))
                    
                    logger.info(f"✅ تم إضافة حساب Ichancy جديد: {account_data['login']}")
                    return True
        
        except Exception as e:
            error_msg = f"❌ فشل إضافة حساب Ichancy: {str(e)}"
            logger.error(error_msg)
            self.log_error(
                user_id=account_data.get('user_id'),
                error_type="add_account_failed",
                error_message=error_msg,
                api_endpoint="database.add_ichancy_account",
                request_data=json.dumps(account_data, default=str)
            )
            return False
    
    def get_ichancy_account(self, user_id: str) -> Optional[Dict]:
        """الحصول على حساب Ichancy للمستخدم"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            SELECT * FROM ichancy_accounts 
                            WHERE user_id = %s AND status = 'active' 
                            ORDER BY created_at DESC LIMIT 1
                        ''', (user_id,))
                    else:
                        cursor.execute('''
                            SELECT * FROM ichancy_accounts 
                            WHERE user_id = ? AND status = 'active' 
                            ORDER BY created_at DESC LIMIT 1
                        ''', (user_id,))
                    
                    result = cursor.fetchone()
                    if result:
                        return dict(result)
                    return None
        
        except Exception as e:
            logger.error(f"❌ فشل جلب حساب Ichancy للمستخدم {user_id}: {str(e)}")
            return None
    
    def update_account_balance(self, player_id: str, new_balance: float) -> bool:
        """تحديث رصيد حساب Ichancy"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            UPDATE ichancy_accounts 
                            SET current_balance = %s, updated_at = %s 
                            WHERE player_id = %s
                        ''', (new_balance, datetime.now(), player_id))
                    else:
                        cursor.execute('''
                            UPDATE ichancy_accounts 
                            SET current_balance = ?, updated_at = ? 
                            WHERE player_id = ?
                        ''', (new_balance, datetime.now(), player_id))
                    
                    logger.info(f"✅ تم تحديث رصيد حساب {player_id}: {new_balance}")
                    return cursor.rowcount > 0
        
        except Exception as e:
            error_msg = f"❌ فشل تحديث رصيد الحساب {player_id}: {str(e)}"
            logger.error(error_msg)
            return False
    
    def get_all_ichancy_logins(self) -> List[str]:
        """الحصول على جميع أسماء المستخدمين"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute("SELECT login FROM ichancy_accounts WHERE login IS NOT NULL")
                    else:
                        cursor.execute("SELECT login FROM ichancy_accounts WHERE login IS NOT NULL")
                    
                    results = cursor.fetchall()
                    return [row['login'] for row in results] if results else []
        
        except Exception as e:
            logger.error(f"❌ فشل جلب أسماء المستخدمين: {str(e)}")
            return []
    
    # ========== إدارة المعاملات ==========
    def add_transaction(self, transaction_data: Dict) -> bool:
        """إضافة معاملة جديدة"""
        try:
            required_fields = ['user_id', 'player_id', 'type', 'amount', 'status']
            for field in required_fields:
                if field not in transaction_data:
                    raise Exception(f"الحقل المطلوب {field} مفقود في بيانات المعاملة")
            
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            INSERT INTO transactions 
                            (user_id, player_id, transaction_type, amount, currency, status, details, error_message, reference_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            transaction_data['user_id'],
                            transaction_data.get('player_id'),
                            transaction_data['type'],
                            transaction_data['amount'],
                            transaction_data.get('currency', 'NSP'),
                            transaction_data['status'],
                            transaction_data.get('details', ''),
                            transaction_data.get('error_message', ''),
                            transaction_data.get('reference_id', '')
                        ))
                    else:
                        cursor.execute('''
                            INSERT INTO transactions 
                            (user_id, player_id, transaction_type, amount, currency, status, details, error_message, reference_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            transaction_data['user_id'],
                            transaction_data.get('player_id'),
                            transaction_data['type'],
                            transaction_data['amount'],
                            transaction_data.get('currency', 'NSP'),
                            transaction_data['status'],
                            transaction_data.get('details', ''),
                            transaction_data.get('error_message', ''),
                            transaction_data.get('reference_id', '')
                        ))
                    
                    logger.info(f"✅ تم إضافة معاملة: {transaction_data['type']} - {transaction_data['amount']} NSP")
                    return True
        
        except Exception as e:
            error_msg = f"❌ فشل إضافة المعاملة: {str(e)}"
            logger.error(error_msg)
            self.log_error(
                user_id=transaction_data.get('user_id'),
                error_type="add_transaction_failed",
                error_message=error_msg,
                api_endpoint="database.add_transaction",
                request_data=json.dumps(transaction_data, default=str)
            )
            return False
    
    def get_user_transactions(self, user_id: str, limit: int = 10) -> List[Dict]:
        """الحصول على معاملات المستخدم"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            SELECT * FROM transactions 
                            WHERE user_id = %s 
                            ORDER BY created_at DESC 
                            LIMIT %s
                        ''', (user_id, limit))
                    else:
                        cursor.execute('''
                            SELECT * FROM transactions 
                            WHERE user_id = ? 
                            ORDER BY created_at DESC 
                            LIMIT ?
                        ''', (user_id, limit))
                    
                    results = cursor.fetchall()
                    return [dict(row) for row in results] if results else []
        
        except Exception as e:
            logger.error(f"❌ فشل جلب معاملات المستخدم {user_id}: {str(e)}")
            return []
    
    # ========== تسجيل الأخطاء ==========
    def log_error(self, **error_data):
        """تسجيل خطأ في قاعدة البيانات"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            INSERT INTO error_logs 
                            (user_id, error_type, error_message, stack_trace, api_endpoint, request_data, response_data)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            error_data.get('user_id'),
                            error_data.get('error_type'),
                            error_data.get('error_message', '')[:500],
                            error_data.get('stack_trace', '')[:2000],
                            error_data.get('api_endpoint'),
                            error_data.get('request_data', '')[:1000],
                            error_data.get('response_data', '')[:1000]
                        ))
                    else:
                        cursor.execute('''
                            INSERT INTO error_logs 
                            (user_id, error_type, error_message, stack_trace, api_endpoint, request_data, response_data)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            error_data.get('user_id'),
                            error_data.get('error_type'),
                            error_data.get('error_message', '')[:500],
                            error_data.get('stack_trace', '')[:2000],
                            error_data.get('api_endpoint'),
                            error_data.get('request_data', '')[:1000],
                            error_data.get('response_data', '')[:1000]
                        ))
        
        except Exception as e:
            logger.error(f"❌ فشل تسجيل الخطأ في قاعدة البيانات: {str(e)}")
    
    # ========== إحصائيات ==========
    def get_user_stats(self, user_id: str) -> Dict:
        """الحصول على إحصائيات المستخدم"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    
                    if self.db_type == "postgresql":
                        # عدد الحسابات النشطة
                        cursor.execute('''
                            SELECT COUNT(*) as count FROM ichancy_accounts 
                            WHERE user_id = %s AND status = 'active'
                        ''', (user_id,))
                        account_count = cursor.fetchone()['count']
                        
                        # إجمالي الإيداعات الناجحة
                        cursor.execute('''
                            SELECT COALESCE(SUM(amount), 0) as total FROM transactions 
                            WHERE user_id = %s AND transaction_type = 'deposit' AND status = 'success'
                        ''', (user_id,))
                        total_deposits = cursor.fetchone()['total']
                        
                        # إجمالي السحوبات الناجحة
                        cursor.execute('''
                            SELECT COALESCE(SUM(amount), 0) as total FROM transactions 
                            WHERE user_id = %s AND transaction_type = 'withdraw' AND status = 'success'
                        ''', (user_id,))
                        total_withdrawals = cursor.fetchone()['total']
                        
                        # عدد المعاملات الفاشلة
                        cursor.execute('''
                            SELECT COUNT(*) as count FROM transactions 
                            WHERE user_id = %s AND status != 'success'
                        ''', (user_id,))
                        failed_transactions = cursor.fetchone()['count']
                    
                    else:
                        # SQLite implementation
                        cursor.execute('''
                            SELECT COUNT(*) as count FROM ichancy_accounts 
                            WHERE user_id = ? AND status = 'active'
                        ''', (user_id,))
                        account_count = cursor.fetchone()['count']
                        
                        cursor.execute('''
                            SELECT COALESCE(SUM(amount), 0) as total FROM transactions 
                            WHERE user_id = ? AND transaction_type = 'deposit' AND status = 'success'
                        ''', (user_id,))
                        total_deposits = cursor.fetchone()['total']
                        
                        cursor.execute('''
                            SELECT COALESCE(SUM(amount), 0) as total FROM transactions 
                            WHERE user_id = ? AND transaction_type = 'withdraw' AND status = 'success'
                        ''', (user_id,))
                        total_withdrawals = cursor.fetchone()['total']
                        
                        cursor.execute('''
                            SELECT COUNT(*) as count FROM transactions 
                            WHERE user_id = ? AND status != 'success'
                        ''', (user_id,))
                        failed_transactions = cursor.fetchone()['count']
                    
                    return {
                        "account_count": account_count or 0,
                        "total_deposits": float(total_deposits or 0),
                        "total_withdrawals": float(total_withdrawals or 0),
                        "failed_transactions": failed_transactions or 0,
                        "net_balance": float((total_deposits or 0) - (total_withdrawals or 0))
                    }
        
        except Exception as e:
            logger.error(f"❌ فشل جلب إحصائيات المستخدم {user_id}: {str(e)}")
            return {}
    
    def cleanup_old_data(self, days: int = 30):
        """تنظيف البيانات القديمة"""
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.db_type == "postgresql":
                        cursor.execute('''
                            DELETE FROM error_logs 
                            WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
                        ''', (days,))
                        deleted_count = cursor.rowcount
                    else:
                        cursor.execute('''
                            DELETE FROM error_logs 
                            WHERE created_at < datetime('now', '-%s days')
                        ''', (days,))
                        deleted_count = cursor.rowcount
                    
                    logger.info(f"✅ تم تنظيف {deleted_count} سجل خطأ قديم")
        
        except Exception as e:
            logger.error(f"❌ فشل تنظيف البيانات القديمة: {str(e)}")

# إنشاء نسخة وحيدة من مدير قاعدة البيانات
db = DatabaseManager()

if __name__ == "__main__":
    # اختبار الاتصال بقاعدة البيانات
    print("🔍 اختبار اتصال قاعدة البيانات...")
    try:
        # اختبار الإضافة والاستعلام
        test_user_id = "test_user_123"
        db.add_user(test_user_id, "test_user")
        
        balance = db.get_user_balance(test_user_id)
        print(f"✅ رصيد المستخدم التجريبي: {balance}")
        
        # اختبار تحديث الرصيد
        db.update_user_balance(test_user_id, 100, "add")
        
        updated_balance = db.get_user_balance(test_user_id)
        print(f"✅ الرصيد بعد الإضافة: {updated_balance}")
        
        # اختبار تسجيل خطأ
        db.log_error(
            user_id=test_user_id,
            error_type="test_error",
            error_message="هذا خطأ تجريبي للاختبار",
            api_endpoint="test.endpoint"
        )
        
        print("🎉 جميع اختبارات قاعدة البيانات تمت بنجاح!")
        
    except Exception as e:
        print(f"❌ فشل اختبار قاعدة البيانات: {str(e)}")
