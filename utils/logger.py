
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from config import config

def setup_logger(name: str = None):
    """إعداد وتسجيل متقدم للبرنامج"""
    
    # إنشاء المسجل
    logger = logging.getLogger(name or __name__)
    logger.setLevel(logging.INFO)
    
    # منع التكرار
    if logger.handlers:
        return logger
    
    # إنشاء مجلد السجلات إذا لم يكن موجوداً
    logs_dir = 'logs'
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # تنسيق السجلات
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # معالج الملف (دوراني)
    log_filename = f"{logs_dir}/ichancy_bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=10*1024*1024,  # 10 ميجابايت
        backupCount=30,  # 30 ملف احتياطي
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # معالج الكونسول
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO if config.IS_PRODUCTION else logging.DEBUG)
    
    # إضافة المعالجات
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # تسجيل معلومات البدء
    logger.info("=" * 50)
    logger.info(f"🚀 بدء تشغيل Ichancy Bot")
    logger.info(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🌐 البيئة: {config.RAILWAY_ENVIRONMENT}")
    logger.info(f"🔧 الوضع: {'إنتاج ⚡' if config.IS_PRODUCTION else 'تطوير 🛠️'}")
    logger.info("=" * 50)
    
    return logger

def setup_error_logger():
    """إعداد مسجل خاص بالأخطاء"""
    
    error_logger = logging.getLogger('error_logger')
    error_logger.setLevel(logging.ERROR)
    
    # منع التكرار
    if error_logger.handlers:
        return error_logger
    
    # إنشاء مجلد أخطاء إذا لم يكن موجوداً
    errors_dir = 'logs/errors'
    if not os.path.exists(errors_dir):
        os.makedirs(errors_dir)
    
    # تنسيق أخطاء
    error_formatter = logging.Formatter(
        '%(asctime)s - ERROR - %(name)s - %(levelname)s - %(message)s\n%(exc_info)s\n' +
        '-'*80 + '\n',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # معالج أخطاء الملف
    error_filename = f"{errors_dir}/errors_{datetime.now().strftime('%Y-%m-%d')}.log"
    error_file_handler = RotatingFileHandler(
        error_filename,
        maxBytes=5*1024*1024,  # 5 ميجابايت
        backupCount=30,
        encoding='utf-8'
    )
    error_file_handler.setFormatter(error_formatter)
    error_file_handler.setLevel(logging.ERROR)
    
    # إضافة المعالج
    error_logger.addHandler(error_file_handler)
    
    return error_logger

def log_api_request(endpoint: str, method: str, payload: dict = None, response: dict = None):
    """تسجيل طلبات API"""
    
    api_logger = logging.getLogger('api_logger')
    
    # منع التكرار
    if not api_logger.handlers:
        api_logger.setLevel(logging.INFO)
        
        # إنشاء مجلد API إذا لم يكن موجوداً
        api_dir = 'logs/api'
        if not os.path.exists(api_dir):
            os.makedirs(api_dir)
        
        # معالج ملف API
        api_filename = f"{api_dir}/api_{datetime.now().strftime('%Y-%m-%d')}.log"
        api_file_handler = RotatingFileHandler(
            api_filename,
            maxBytes=5*1024*1024,
            backupCount=30,
            encoding='utf-8'
        )
        
        api_formatter = logging.Formatter(
            '%(asctime)s - API - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        api_file_handler.setFormatter(api_formatter)
        api_logger.addHandler(api_file_handler)
    
    # تسجيل الطلب
    log_message = f"{method} {endpoint}"
    if payload:
        log_message += f" | Payload: {str(payload)[:500]}"
    if response:
        log_message += f" | Response: {str(response)[:500]}"
    
    api_logger.info(log_message)

def log_user_activity(user_id: str, action: str, details: str = None):
    """تسجيل أنشطة المستخدمين"""
    
    activity_logger = logging.getLogger('activity_logger')
    
    # منع التكرار
    if not activity_logger.handlers:
        activity_logger.setLevel(logging.INFO)
        
        # إنشاء مجلد الأنشطة إذا لم يكن موجوداً
        activity_dir = 'logs/activity'
        if not os.path.exists(activity_dir):
            os.makedirs(activity_dir)
        
        # معالج ملف الأنشطة
        activity_filename = f"{activity_dir}/activity_{datetime.now().strftime('%Y-%m-%d')}.log"
        activity_file_handler = RotatingFileHandler(
            activity_filename,
            maxBytes=10*1024*1024,
            backupCount=30,
            encoding='utf-8'
        )
        
        activity_formatter = logging.Formatter(
            '%(asctime)s - ACTIVITY - User: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        activity_file_handler.setFormatter(activity_formatter)
        activity_logger.addHandler(activity_file_handler)
    
    # تسجيل النشاط
    log_message = f"{user_id} - {action}"
    if details:
        log_message += f" | Details: {details}"
    
    activity_logger.info(log_message)

def get_log_files():
    """الحصول على قائمة ملفات السجلات"""
    
    logs = []
    
    try:
        # مجلد السجلات الرئيسي
        if os.path.exists('logs'):
            for root, dirs, files in os.walk('logs'):
                for file in files:
                    if file.endswith('.log'):
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        logs.append({
                            'path': file_path,
                            'name': file,
                            'size': file_size,
                            'relative_path': os.path.relpath(file_path, 'logs')
                        })
    
    except Exception as e:
        logging.error(f"❌ فشل جلب ملفات السجلات: {str(e)}")
    
    return logs

def cleanup_old_logs(days: int = 30):
    """تنظيف السجلات القديمة"""
    
    try:
        from datetime import datetime, timedelta
        import os
        import glob
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        log_patterns = [
            'logs/*.log',
            'logs/errors/*.log',
            'logs/api/*.log',
            'logs/activity/*.log'
        ]
        
        deleted_count = 0
        
        for pattern in log_patterns:
            for log_file in glob.glob(pattern):
                try:
                    # الحصول على وقت الملف
                    file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
                    
                    # حذف الملف إذا كان قديماً
                    if file_time < cutoff_date:
                        os.remove(log_file)
                        deleted_count += 1
                        logging.info(f"🧹 تم حذف سجل قديم: {log_file}")
                
                except Exception as e:
                    logging.error(f"❌ فشل حذف السجل {log_file}: {str(e)}")
        
        logging.info(f"✅ تم تنظيف {deleted_count} ملف سجل قديم")
        return deleted_count
        
    except Exception as e:
        logging.error(f"❌ فشل تنظيف السجلات القديمة: {str(e)}")
        return 0

if __name__ == "__main__":
    # اختبار نظام التسجيل
    print("🔍 اختبار نظام التسجيل...")
    
    logger = setup_logger('test_logger')
    
    logger.debug("هذه رسالة تحقق")
    logger.info("هذه رسالة معلومات")
    logger.warning("هذه رسالة تحذير")
    logger.error("هذه رسالة خطأ")
    
    # اختبار تسجيل API
    log_api_request('/api/test', 'GET', {'test': 'data'}, {'result': 'success'})
    
    # اختبار تسجيل النشاط
    log_user_activity('test_user', 'login', 'تم تسجيل الدخول بنجاح')
    
    print("✅ تم اختبار نظام التسجيل بنجاح!")
    
    # عرض ملفات السجلات
    log_files = get_log_files()
    print(f"📁 عدد ملفات السجلات: {len(log_files)}")
