
# utils/helpers.py
"""
أدوات مساعدة للتطبيق - دوال عامة للتعامل مع البيانات والتنسيق
"""

import re
import random
import string
import hashlib
import json
import time
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple
from decimal import Decimal, ROUND_HALF_UP
from config import config

# ========== دوال تنسيق البيانات ==========

def format_currency(amount: Union[float, int, str], currency: str = "NSP") -> str:
    """تنسيق العملة بشكل جميل"""
    
    try:
        # تحويل إلى عدد عشري للدقة
        if isinstance(amount, str):
            amount = float(amount)
        
        amount_decimal = Decimal(str(amount))
        
        # تقريب إلى منزلتين عشريتين
        amount_decimal = amount_decimal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # تنسيق مع فواصل الآلاف
        amount_str = f"{amount_decimal:,.2f}"
        
        # رموز العملات
        currency_symbols = {
            "NSP": "₪",
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "SAR": "ر.س",
            "AED": "د.إ",
            "QAR": "ر.ق"
        }
        
        symbol = currency_symbols.get(currency, currency)
        
        return f"{amount_str} {symbol}"
        
    except (ValueError, TypeError):
        return f"0.00 {currency}"

def format_date(date_string: Optional[str] = None, 
                format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """تنسيق التاريخ والوقت"""
    
    if date_string:
        try:
            if isinstance(date_string, str):
                # محاولة تحليل التاريخ من تنسيقات مختلفة
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%H:%M:%S"]:
                    try:
                        dt = datetime.strptime(date_string, fmt)
                        return dt.strftime(format_str)
                    except ValueError:
                        continue
            
            # إذا كان كائن datetime
            if isinstance(date_string, datetime):
                return date_string.strftime(format_str)
                
        except Exception:
            pass
    
    # التاريخ الحالي إذا فشل التحليل
    return datetime.now().strftime(format_str)

def format_time_ago(timestamp: Union[str, datetime]) -> str:
    """تنسيق الوقت الماضي (مثل: منذ 5 دقائق)"""
    
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return "غير معروف"
        
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 365:
            years = diff.days // 365
            return f"منذ {years} سنة" if years == 1 else f"منذ {years} سنوات"
        elif diff.days > 30:
            months = diff.days // 30
            return f"منذ {months} شهر" if months == 1 else f"منذ {months} أشهر"
        elif diff.days > 0:
            return f"منذ {diff.days} يوم" if diff.days == 1 else f"منذ {diff.days} أيام"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"منذ {hours} ساعة" if hours == 1 else f"منذ {hours} ساعات"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"منذ {minutes} دقيقة" if minutes == 1 else f"منذ {minutes} دقائق"
        else:
            return "الآن"
            
    except Exception:
        return "غير معروف"

def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """تقصير النص إذا كان أطول من الحد الأقصى"""
    
    if not text:
        return ""
    
    text = str(text)
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

# ========== دوال التحقق ==========

def validate_email(email: str) -> bool:
    """التحقق من صحة عنوان البريد الإلكتروني"""
    
    if not email:
        return False
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))

def validate_phone(phone: str) -> bool:
    """التحقق من صحة رقم الهاتف"""
    
    if not phone:
        return False
    
    # نمط عام لأرقام الهواتف الدولية
    phone_pattern = r'^[\+]?[0-9]{10,15}$'
    return bool(re.match(phone_pattern, phone))

def validate_username(username: str) -> Tuple[bool, str]:
    """التحقق من صحة اسم المستخدم مع رسالة خطأ"""
    
    if not username:
        return False, "اسم المستخدم مطلوب"
    
    # التحقق من الطول
    if len(username) < 3:
        return False, "اسم المستخدم قصير جداً (الحد الأدنى 3 أحرف)"
    
    if len(username) > 20:
        return False, "اسم المستخدم طويل جداً (الحد الأقصى 20 حرفاً)"
    
    # التحقق من الأحرف المسموحة
    if not re.match(r'^[a-zA-Z0-9._-]+$', username):
        return False, "يحتوي على أحرف غير مسموحة. استخدم الأحرف اللاتينية والأرقام والنقاط والشرطات فقط"
    
    # التحقق من أن يبدأ بحرف
    if not username[0].isalpha():
        return False, "يجب أن يبدأ اسم المستخدم بحرف لاتيني"
    
    # التحقق من عدم احتواء على كلمات محجوزة
    reserved_words = ['admin', 'root', 'system', 'support', 'ichancy', 'agent']
    if username.lower() in reserved_words:
        return False, "اسم المستخدم محجوز"
    
    return True, "اسم المستخدم صالح"

def validate_password(password: str) -> Tuple[bool, str]:
    """التحقق من صحة كلمة المرور مع رسالة خطأ"""
    
    if not password:
        return False, "كلمة المرور مطلوبة"
    
    min_len = config.APP_CONFIG.get('min_password_length', 8)
    max_len = config.APP_CONFIG.get('max_password_length', 11)
    
    # التحقق من الطول
    if len(password) < min_len:
        return False, f"كلمة المرور قصيرة جداً (الحد الأدنى {min_len} أحرف)"
    
    if len(password) > max_len:
        return False, f"كلمة المرور طويلة جداً (الحد الأقصى {max_len} أحرف)"
    
    # التحقق من الأحرف المسموحة
    if not re.match(r'^[A-Za-z0-9@#$%^&*]+$', password):
        return False, "يحتوي على أحرف غير مسموحة. استخدم الأحرف اللاتينية والأرقام والرموز (@#$%^&*) فقط"
    
    # التحقق من وجود حرف واحد على الأقل
    if not any(c.isalpha() for c in password):
        return False, "يجب أن تحتوي على حرف واحد على الأقل"
    
    # تحسين: التحقق من وجود رقم
    if not any(c.isdigit() for c in password):
        return False, "يجب أن تحتوي على رقم واحد على الأقل"
    
    return True, "كلمة المرور صالحة"

# ========== دوال توليد البيانات ==========

def generate_random_string(length: int = 8, 
                          include_digits: bool = True,
                          include_symbols: bool = False) -> str:
    """توليد سلسلة عشوائية"""
    
    characters = string.ascii_letters
    
    if include_digits:
        characters += string.digits
    
    if include_symbols:
        characters += "@#$%^&*"
    
    return ''.join(random.choice(characters) for _ in range(length))

def generate_unique_id(prefix: str = "", length: int = 12) -> str:
    """توليد معرف فريد"""
    
    timestamp = int(time.time() * 1000)
    random_part = generate_random_string(length // 2, include_digits=True)
    
    unique_id = f"{timestamp}{random_part}"
    
    if prefix:
        unique_id = f"{prefix}_{unique_id}"
    
    return unique_id[:length]

def generate_transaction_id() -> str:
    """توليد معرف معاملة"""
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = generate_random_string(6, include_digits=True)
    
    return f"TXN_{timestamp}_{random_part}"

def generate_player_email(username: str) -> str:
    """توليد إيميل لاعب"""
    
    return f"{username}@TSA.com"

# ========== دوال التشفير والأمان ==========

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """تشفير كلمة المرور مع الملح"""
    
    if not salt:
        salt = generate_random_string(16, include_digits=True)
    
    # استخدام SHA-256 للتشفير
    hash_obj = hashlib.sha256()
    hash_obj.update(f"{password}{salt}".encode('utf-8'))
    hashed_password = hash_obj.hexdigest()
    
    return hashed_password, salt

def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """التحقق من كلمة المرور"""
    
    test_hash, _ = hash_password(password, salt)
    return test_hash == hashed_password

def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """إخفاء البيانات الحساسة (مثل أرقام البطاقات)"""
    
    if not data or len(data) <= visible_chars:
        return "***"
    
    return f"{data[:visible_chars]}{'*' * (len(data) - visible_chars)}"

def sanitize_input(input_str: str, max_length: int = 500) -> str:
    """تنظيف وإزالة الأحرف الخطرة من الإدخال"""
    
    if not input_str:
        return ""
    
    # إزالة الأحرف الخطرة
    dangerous_chars = ['<', '>', '&', '"', "'", '`', ';']
    for char in dangerous_chars:
        input_str = input_str.replace(char, '')
    
    # تقييد الطول
    if len(input_str) > max_length:
        input_str = input_str[:max_length]
    
    return input_str.strip()

# ========== دوال التعامل مع الأرقام ==========

def safe_float_convert(value: Any, default: float = 0.0) -> float:
    """تحويل آمن إلى عدد عشري"""
    
    try:
        if value is None:
            return default
        
        if isinstance(value, (int, float)):
            return float(value)
        
        if isinstance(value, str):
            # إزالة أي أحرف غير رقمية باستثناء النقطة
            cleaned = re.sub(r'[^\d.-]', '', value)
            if cleaned:
                return float(cleaned)
        
        return default
        
    except (ValueError, TypeError):
        return default

def calculate_percentage(part: float, total: float, decimals: int = 2) -> float:
    """حساب النسبة المئوية"""
    
    if total == 0:
        return 0.0
    
    percentage = (part / total) * 100
    return round(percentage, decimals)

def format_percentage(value: float, decimals: int = 2) -> str:
    """تنسيق النسبة المئوية"""
    
    return f"{value:.{decimals}f}%"

def calculate_fee(amount: float, fee_percentage: float = 0.0) -> Dict[str, float]:
    """حساب الرسوم"""
    
    fee_amount = (amount * fee_percentage) / 100
    net_amount = amount - fee_amount
    
    return {
        'original': amount,
        'fee_percentage': fee_percentage,
        'fee_amount': round(fee_amount, 2),
        'net_amount': round(net_amount, 2)
    }

# ========== دوال الوقت والتأخير ==========

def human_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """تأخير عشوائي يشبه السلوك البشري"""
    
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

def format_duration(seconds: int) -> str:
    """تنسيق المدة الزمنية"""
    
    if seconds < 60:
        return f"{seconds} ثانية"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} دقيقة"
    
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ساعة"
    
    days = hours // 24
    return f"{days} يوم"

def is_business_hours() -> bool:
    """التحقق إذا كان الوقت ضمن ساعات العمل"""
    
    now = datetime.now()
    
    # أيام الأسبوع (0 = الإثنين، 6 = الأحد)
    weekday = now.weekday()
    
    # الوقت الحالي
    current_time = now.time()
    
    # ساعات العمل: الأحد - الخميس، 9 ص - 5 م
    start_time = datetime.strptime("09:00", "%H:%M").time()
    end_time = datetime.strptime("17:00", "%H:%M").time()
    
    # نهاية الأسبوع (الجمعة والسبت)
    if weekday >= 4:  # 4 = الجمعة، 5 = السبت
        return False
    
    return start_time <= current_time <= end_time

# ========== دوال التعامل مع JSON ==========

def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """تحميل JSON بشكل آمن"""
    
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default

def safe_json_dumps(data: Any, ensure_ascii: bool = False, **kwargs) -> str:
    """تحويل إلى JSON بشكل آمن"""
    
    try:
        return json.dumps(data, ensure_ascii=ensure_ascii, default=str, **kwargs)
    except (TypeError, ValueError):
        return "{}"

def filter_sensitive_data(data: Dict) -> Dict:
    """تصفية البيانات الحساسة من القاموس"""
    
    if not isinstance(data, dict):
        return data
    
    filtered = data.copy()
    sensitive_keys = ['password', 'token', 'secret', 'key', 'authorization']
    
    for key in filtered.keys():
        key_lower = key.lower()
        for sensitive in sensitive_keys:
            if sensitive in key_lower:
                filtered[key] = '***HIDDEN***'
                break
    
    return filtered

# ========== دوال التحويل ==========

def convert_currency(amount: float, from_currency: str, to_currency: str) -> Optional[float]:
    """تحويل العملة (بسيط - يحتاج إلى تحديث بالأسعار الفعلية)"""
    
    # أسعار صرف افتراضية
    exchange_rates = {
        "USD_NSP": 3.5,
        "EUR_NSP": 4.0,
        "GBP_NSP": 4.5,
        "SAR_NSP": 0.93,
        "AED_NSP": 0.95,
        "QAR_NSP": 0.96
    }
    
    if from_currency == to_currency:
        return amount
    
    key = f"{from_currency}_{to_currency}"
    reverse_key = f"{to_currency}_{from_currency}"
    
    if key in exchange_rates:
        return amount * exchange_rates[key]
    elif reverse_key in exchange_rates:
        return amount / exchange_rates[reverse_key]
    
    return None

def bytes_to_human_readable(size_bytes: int) -> str:
    """تحويل حجم الملف إلى تنسيق مقروء"""
    
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    
    return f"{s} {size_names[i]}"

# ========== دوال متنوعة ==========

def get_emoji_for_status(status: str) -> str:
    """الحصول على إيموجي مناسب للحالة"""
    
    status_emojis = {
        'success': '✅',
        'failed': '❌',
        'pending': '⏳',
        'processing': '⚡',
        'active': '🟢',
        'inactive': '🔴',
        'warning': '⚠️',
        'info': 'ℹ️',
        'error': '🚨',
        'completed': '🎉'
    }
    
    return status_emojis.get(status.lower(), '📝')

def generate_progress_bar(percentage: float, length: int = 10) -> str:
    """إنشاء شريط تقدم"""
    
    percentage = max(0, min(100, percentage))
    filled = int(percentage / 100 * length)
    empty = length - filled
    
    return f"[{'█' * filled}{'░' * empty}] {percentage:.1f}%"

def validate_amount(amount: Union[str, float, int], 
                   min_amount: float = None, 
                   max_amount: float = None) -> Tuple[bool, str, float]:
    """التحقق من صحة المبلغ"""
    
    try:
        # تحويل إلى float
        if isinstance(amount, str):
            amount_float = float(amount)
        else:
            amount_float = float(amount)
        
        # التحقق من أن المبلغ موجب
        if amount_float <= 0:
            return False, "المبلغ يجب أن يكون أكبر من صفر", 0.0
        
        # التحقق من الحد الأدنى
        if min_amount is not None and amount_float < min_amount:
            return False, f"المبلغ أقل من الحد الأدنى ({min_amount} NSP)", 0.0
        
        # التحقق من الحد الأقصى
        if max_amount is not None and amount_float > max_amount:
            return False, f"المبلغ يتجاوز الحد الأقصى ({max_amount} NSP)", 0.0
        
        # تقريب إلى منزلتين عشريتين
        amount_float = round(amount_float, 2)
        
        return True, "المبلغ صالح", amount_float
        
    except (ValueError, TypeError):
        return False, "المبلغ غير صالح", 0.0

def create_pagination_buttons(current_page: int, total_pages: int, 
                            callback_prefix: str = "page") -> List[List[Dict]]:
    """إنشاء أزرار التصفح"""
    
    keyboard = []
    row = []
    
    # زر الصفحة السابقة
    if current_page > 1:
        row.append({
            "text": "⬅️ السابق",
            "callback_data": f"{callback_prefix}_{current_page - 1}"
        })
    
    # عرض الصفحة الحالية
    row.append({
        "text": f"📄 {current_page}/{total_pages}",
        "callback_data": "current_page"
    })
    
    # زر الصفحة التالية
    if current_page < total_pages:
        row.append({
            "text": "التالي ➡️",
            "callback_data": f"{callback_prefix}_{current_page + 1}"
        })
    
    if row:
        keyboard.append(row)
    
    # زر العودة
    keyboard.append([{
        "text": "🔙 العودة",
        "callback_data": "main_menu"
    }])
    
    return keyboard

def extract_username_from_email(email: str) -> str:
    """استخراج اسم المستخدم من الإيميل"""
    
    if not email or '@' not in email:
        return email or ""
    
    return email.split('@')[0]

def generate_otp(length: int = 6) -> str:
    """توليد رمز OTP"""
    
    return ''.join(random.choice(string.digits) for _ in range(length))

def is_valid_url(url: str) -> bool:
    """التحقق من صحة الرابط"""
    
    if not url:
        return False
    
    url_pattern = r'^(https?://)?([\da-z.-]+)\.([a-z.]{2,6})([/\w .-]*)*/?$'
    return bool(re.match(url_pattern, url))

# ========== اختبار الدوال ==========

if __name__ == "__main__":
    print("🔍 اختبار أدوات المساعدة...")
    
    # اختبار تنسيق العملة
    print(f"💰 تنسيق العملة: {format_currency(1234567.89)}")
    
    # اختبار تنسيق التاريخ
    print(f"📅 تنسيق التاريخ: {format_date()}")
    
    # اختبار التحقق من اسم المستخدم
    test_usernames = ["john", "john_doe", "123user", "user@name", "ab"]
    for username in test_usernames:
        valid, msg = validate_username(username)
        print(f"👤 {username}: {'✅' if valid else '❌'} {msg}")
    
    # اختبار توليد بيانات
    print(f"🔑 معرف فريد: {generate_unique_id('USER')}")
    print(f"💳 معرف معاملة: {generate_transaction_id()}")
    print(f"📧 إيميل لاعب: {generate_player_email('test_user')}")
    
    # اختبار التحقق من المبلغ
    test_amounts = [("50", 10, 100), ("-10", 0, 100), ("abc", 0, 100)]
    for amount_str, min_amt, max_amt in test_amounts:
        valid, msg, amount = validate_amount(amount_str, min_amt, max_amt)
        print(f"💰 {amount_str}: {'✅' if valid else '❌'} {msg}")
    
    print("\n✅ جميع الاختبارات تمت بنجاح!")
