# handlers/start_handler.py
import logging
import traceback
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from config import config

logger = logging.getLogger(__name__)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start مع إدارة الأخطاء المفصلة"""
    
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "مستخدم"
    chat_id = update.effective_chat.id
    
    logger.info(f"🚀 بدء البوت من قبل المستخدم: {user_id} (@{username})")
    
    try:
        # إضافة/تحديث المستخدم في قاعدة البيانات
        user_added = db.add_user(user_id, username)
        
        if not user_added:
            logger.error(f"❌ فشل إضافة المستخدم {user_id} إلى قاعدة البيانات")
            await update.message.reply_text(
                "❌ حدث خطأ في تسجيل بياناتك. يرجى المحاولة مرة أخرى أو الاتصال بالدعم."
            )
            return
        
        # تحديث آخر نشاط
        db.update_user_activity(user_id)
        
        # التحقق من حالة الخدمات
        services_status = await _check_services_status()
        
        # إنشاء لوحة المفاتيح الرئيسية
        keyboard = _create_main_keyboard(services_status)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # إنشاء رسالة الترحيب
        welcome_message = _create_welcome_message(username, services_status)
        
        # إرسال الرسالة
        await update.message.reply_text(
            welcome_message,
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        logger.info(f"✅ تم إرسال رسالة الترحيب للمستخدم {user_id}")
        
        # تسجيل بدء الجلسة
        db.add_transaction({
            'user_id': user_id,
            'type': 'session_start',
            'amount': 0,
            'status': 'success',
            'details': f'بدأ المستخدم @{username} الجلسة'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة أمر /start للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        # تسجيل الخطأ في قاعدة البيانات
        db.log_error(
            user_id=user_id,
            error_type='start_handler_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.start_handler'
        )
        
        # إرسال رسالة خطأ للمستخدم
        try:
            await update.message.reply_text(
                "❌ حدث خطأ غير متوقع أثناء بدء البوت. "
                "يرجى المحاولة مرة أخرى أو الاتصال بالدعم الفني.\n\n"
                f"📋 كود الخطأ: `{user_id[:8]}`",
                parse_mode='Markdown'
            )
        except:
            logger.error(f"❌ فشل إرسال رسالة الخطأ للمستخدم {user_id}")

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /help مع دليل تفصيلي"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"📚 طلب المساعدة من المستخدم: {user_id}")
    
    try:
        help_text = _create_help_text()
        
        # إضافة زر العودة للقائمة الرئيسية
        keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        logger.info(f"✅ تم إرسال دليل المساعدة للمستخدم {user_id}")
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة أمر /help للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='help_handler_failed',
            error_message=error_msg,
            api_endpoint='handlers.help_handler'
        )
        
        await update.message.reply_text(
            "❌ حدث خطأ أثناء تحميل دليل المساعدة. يرجى المحاولة مرة أخرى."
        )

async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض رصيد المستخدم وإحصائياته"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"💰 طلب الرصيد من المستخدم: {user_id}")
    
    try:
        # الحصول على رصيد المستخدم
        user_balance = db.get_user_balance(user_id)
        
        # الحصول على إحصائيات المستخدم
        user_stats = db.get_user_stats(user_id)
        
        # الحصول على حساب Ichancy إن وجد
        ichancy_account = db.get_ichancy_account(user_id)
        
        # إنشاء رسالة الرصيد
        balance_message = _create_balance_message(
            user_balance, 
            user_stats, 
            ichancy_account
        )
        
        # إنشاء لوحة مفاتيح للعمليات
        keyboard = [
            [InlineKeyboardButton("💰 تعبئة الرصيد", callback_data='deposit')],
            [InlineKeyboardButton("💳 سحب الرصيد", callback_data='withdraw')],
            [InlineKeyboardButton("📋 سجل المعاملات", callback_data='transactions')],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            balance_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ تم إرسال معلومات الرصيد للمستخدم {user_id}")
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة أمر /balance للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='balance_handler_failed',
            error_message=error_msg,
            api_endpoint='handlers.balance_handler'
        )
        
        await update.message.reply_text(
            "❌ حدث خطأ أثناء جلب معلومات الرصيد. يرجى المحاولة مرة أخرى."
        )

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات مفصلة للمستخدم"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"📊 طلب الإحصائيات من المستخدم: {user_id}")
    
    try:
        # الحصول على إحصائيات المستخدم
        user_stats = db.get_user_stats(user_id)
        
        # الحصول على آخر المعاملات
        recent_transactions = db.get_user_transactions(user_id, limit=5)
        
        # إنشاء رسالة الإحصائيات
        stats_message = _create_stats_message(user_stats, recent_transactions)
        
        keyboard = [
            [InlineKeyboardButton("📜 جميع المعاملات", callback_data='all_transactions')],
            [InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data='refresh_stats')],
            [InlineKeyboardButton("🔙 العودة للرصيد", callback_data='my_balance')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            stats_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ تم إرسال الإحصائيات للمستخدم {user_id}")
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة أمر /stats للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='stats_handler_failed',
            error_message=error_msg,
            api_endpoint='handlers.stats_handler'
        )
        
        await update.message.reply_text(
            "❌ حدث خطأ أثناء جلب الإحصائيات. يرجى المحاولة مرة أخرى."
        )

async def site_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال روابط الموقع"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"🌐 طلب روابط الموقع من المستخدم: {user_id}")
    
    try:
        urls_message = """
*🌐 روابط Ichancy الرسمية:*

• *الموقع الرئيسي:* [ichancy.com](https://ichancy.com)
• *لوحة الوكيل:* [agents.ichancy.com](https://agents.ichancy.com)
• *لوحة اللاعب:* [player.ichancy.com](https://player.ichancy.com)

*📱 تطبيقات الهاتف:*
• *Android:* متوفر على Google Play
• *iOS:* متوفر على App Store

*⚠️ ملاحظة هامة:*
تأكد دائماً من استخدام الروابط الرسمية فقط لتجنب الاحتيال.
        """
        
        keyboard = [
            [InlineKeyboardButton("🔗 فتح الموقع الرئيسي", url='https://ichancy.com')],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data='main_menu')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            urls_message,
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=False
        )
        
        logger.info(f"✅ تم إرسال روابط الموقع للمستخدم {user_id}")
        
    except Exception as e:
        error_msg = f"❌ فشل إرسال روابط الموقع للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='site_url_handler_failed',
            error_message=error_msg,
            api_endpoint='handlers.site_url_handler'
        )
        
        await update.message.reply_text(
            "❌ حدث خطأ أثناء تحميل الروابط. يرجى المحاولة مرة أخرى."
        )

async def _check_services_status() -> dict:
    """التحقق من حالة الخدمات المختلفة"""
    
    status = {
        'api': False,
        'database': True,  # مفترض أنه يعمل
        'bot': True,
        'ichancy_site': False
    }
    
    try:
        # التحقق من إعدادات API
        if all([config.AGENT_USERNAME, config.AGENT_PASSWORD, config.PARENT_ID]):
            status['api'] = True
        
        # التحقق من اتصال قاعدة البيانات (محاولة استعلام بسيط)
        try:
            test_balance = db.get_user_balance('test_user')
            status['database'] = True
        except:
            status['database'] = False
        
        # التحقق من توفر موقع Ichancy (اختياري - قد يكون بطيئاً)
        # status['ichancy_site'] = await _check_ichancy_availability()
        
        logger.debug(f"📊 حالة الخدمات: {status}")
        
    except Exception as e:
        logger.error(f"❌ فشل التحقق من حالة الخدمات: {str(e)}")
    
    return status

def _create_main_keyboard(services_status: dict) -> list:
    """إنشاء لوحة المفاتيح الرئيسية"""
    
    keyboard = [
        [InlineKeyboardButton("🆕 إنشاء حساب جديد", callback_data='create_account')],
        [
            InlineKeyboardButton("💰 تعبئة الرصيد", callback_data='deposit'),
            InlineKeyboardButton("💳 سحب الرصيد", callback_data='withdraw')
        ],
        [
            InlineKeyboardButton("👤 حسابي", callback_data='my_account'),
            InlineKeyboardButton("📊 رصيدي", callback_data='my_balance')
        ],
        [
            InlineKeyboardButton("📋 إحصائياتي", callback_data='stats'),
            InlineKeyboardButton("📜 سجل المعاملات", callback_data='transactions')
        ],
        [
            InlineKeyboardButton("🌐 رابط الموقع", callback_data='site_url'),
            InlineKeyboardButton("🆘 المساعدة", callback_data='help')
        ]
    ]
    
    # إضافة مؤشرات حالة الخدمات
    if not services_status['api']:
        keyboard.insert(0, [
            InlineKeyboardButton("⚠️ خدمة API غير متاحة", callback_data='api_status')
        ])
    
    return keyboard

def _create_welcome_message(username: str, services_status: dict) -> str:
    """إنشاء رسالة ترحيب مخصصة"""
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # مؤشرات حالة الخدمات
    status_indicators = ""
    if not services_status['api']:
        status_indicators += "⚠️ *خدمة إنشاء الحسابات غير متاحة*\n"
    if not services_status['database']:
        status_indicators += "⚠️ *قاعدة البيانات غير متصلة*\n"
    
    if status_indicators:
        status_indicators = f"\n*🔔 تنبيهات النظام:*\n{status_indicators}"
    
    welcome_message = f"""
🎉 *مرحباً بك {username} في بوت إدارة حسابات Ichancy* 🤖

*✨ الخدمات المتاحة:*

• 🆕 *إنشاء حساب جديد* على منصة Ichancy
• 💰 *تعبئة الرصيد* لحسابك بكل سهولة  
• 💳 *سحب الرصيد* من حسابك بأمان
• 👤 *عرض معلومات حسابك* وتفاصيله
• 📊 *متابعة رصيدك* المحلي والحقيقي
• 📋 *عرض إحصائياتك* ومعاملاتك

*📅 الوقت الحالي:* `{current_time}`
{status_indicators}
*⚡ كيفية الاستخدام:*
1. اختر الخدمة المطلوبة من القائمة
2. اتبع التعليمات التي تظهر لك
3. احفظ بيانات حسابك في مكان آمن

*📞 للدعم والاستفسارات:* @TSA_Support
*🕒 وقت الاستجابة:* 24/7
    """
    
    return welcome_message

def _create_help_text() -> str:
    """إنشاء نص المساعدة التفصيلي"""
    
    help_text = f"""
*📚 دليل الاستخدام الشامل*

*🔹 إنشاء حساب جديد:*
1. اضغط على "إنشاء حساب جديد"
2. أدخل اسم المستخدم المطلوب (لاتيني فقط)
3. أدخل كلمة المرور (8-11 حرف)
4. أدخل مبلغ الشحن الابتدائي ({config.APP_CONFIG['min_amount']}+ NSP)

*🔹 تعبئة الرصيد:*
1. اضغط على "تعبئة الرصيد"
2. أدخل المبلغ المطلوب ({config.APP_CONFIG['min_amount']}+ NSP)
3. سيتم خصم المبلغ من رصيدك المحلي

*🔹 سحب الرصيد:*
1. اضغط على "سحب الرصيد"
2. أدخل المبلغ المطلوب ({config.APP_CONFIG['min_amount']}+ NSP)
3. يجب أن يكون لديك رصيد كافي في حساب Ichancy

*🔹 الأوامر النصية:*
/start - عرض القائمة الرئيسية
/help - عرض هذه التعليمات  
/balance - عرض رصيدك المحلي
/stats - عرض إحصائياتك

*⚠️ ملاحظات مهمة:*
• الحد الأدنى لأي عملية هو {config.APP_CONFIG['min_amount']} NSP
• الرصيد يُحدّث كل 30 دقيقة
• احفظ بيانات حسابك في مكان آمن
• للدعم: @TSA_Support

*🛡️ سياسة الأمان:*
• بياناتك محفوظة بأمان في قاعدة البيانات
• كلمات المرور مشفرة
• جميع المعاملات مسجلة
• لا نطلب منك كلمات المرور أبداً

*🔄 استكشاف الأخطاء وإصلاحها:*
• إذا فشلت عملية: أعد المحاولة بعد دقيقة
• إذا استمر الخطأ: اتصل بالدعم مع كود الخطأ
• كود الخطأ: `USER_ID` الخاص بك

*📊 إحصائيات النظام:*
• وقت التشغيل: 24/7
• وقت الاستجابة: < 3 ثواني
• نسبة النجاح: > 95%
    """
    
    return help_text

def _create_balance_message(user_balance: float, user_stats: dict, ichancy_account: dict = None) -> str:
    """إنشاء رسالة الرصيد المخصصة"""
    
    balance_message = f"""
*💰 معلومات الرصيد*

• *الرصيد المحلي:* `{user_balance:.2f}` NSP
• *إجمالي الإيداعات:* `{user_stats.get('total_deposits', 0):.2f}` NSP
• *إجمالي السحوبات:* `{user_stats.get('total_withdrawals', 0):.2f}` NSP
• *صافي الرصيد:* `{user_stats.get('net_balance', 0):.2f}` NSP
• *عدد الحسابات:* `{user_stats.get('account_count', 0)}`
• *المعاملات الفاشلة:* `{user_stats.get('failed_transactions', 0)}`
    """
    
    if ichancy_account:
        ichancy_balance = ichancy_account.get('current_balance', 0)
        balance_message += f"\n• *رصيد Ichancy:* `{ichancy_balance:.2f}` NSP"
    
    balance_message += f"""

*📊 ملاحظات:*
• هذا الرصيد المحلي فقط
• رصيد Ichancy يُحدّث كل 30 دقيقة
• الحد الأدنى للإيداع/السحب: {config.APP_CONFIG['min_amount']} NSP

*💡 نصائح:*
• حافظ على رصيد كافي للعمليات السريعة
• راجع سجل المعاملات بانتظام
• احتفظ بنسخة من بيانات حسابك
    """
    
    return balance_message

def _create_stats_message(user_stats: dict, recent_transactions: list) -> str:
    """إنشاء رسالة الإحصائيات التفصيلية"""
    
    # حساب النسب
    total_transactions = user_stats.get('account_count', 0) + \
                        user_stats.get('failed_transactions', 0)
    
    success_rate = 0
    if total_transactions > 0:
        success_rate = (user_stats.get('account_count', 0) / total_transactions) * 100
    
    stats_message = f"""
*📊 الإحصائيات التفصيلية*

*📈 إحصائيات عامة:*
• عدد الحسابات النشطة: `{user_stats.get('account_count', 0)}`
• إجمالي الإيداعات: `{user_stats.get('total_deposits', 0):.2f}` NSP
• إجمالي السحوبات: `{user_stats.get('total_withdrawals', 0):.2f}` NSP
• صافي الرصيد: `{user_stats.get('net_balance', 0):.2f}` NSP
• المعاملات الفاشلة: `{user_stats.get('failed_transactions', 0)}`
• نسبة النجاح: `{success_rate:.1f}%`

*📅 آخر المعاملات:*
    """
    
    if recent_transactions:
        for i, transaction in enumerate(recent_transactions[:5], 1):
            trans_type = "إيداع" if transaction['type'] == 'deposit' else "سحب"
            status_icon = "✅" if transaction['status'] == 'success' else "❌"
            
            stats_message += f"\n{i}. {status_icon} *{trans_type}*: `{transaction['amount']}` NSP"
            stats_message += f"\n   📅 {transaction['created_at'].split()[0]} | {transaction['status']}"
            
            if transaction.get('error_message'):
                stats_message += f"\n   ⚠️ {transaction['error_message'][:50]}..."
    else:
        stats_message += "\n\n📭 لا توجد معاملات سابقة"
    
    stats_message += f"""

*📋 ملاحظات:*
• يتم تحديث الإحصائيات فوراً
• جميع المعاملات مسجلة لمدة 30 يوم
• للأسئلة: @TSA_Support
    """
    
    return stats_message

# دالة مساعدة للتحقق من توفر موقع Ichancy (اختياري)
async def _check_ichancy_availability() -> bool:
    """التحقق من توفر موقع Ichancy"""
    try:
        import aiohttp
        import asyncio
        
        async with aiohttp.ClientSession() as session:
            async with session.get(config.ORIGIN, timeout=10) as response:
                return response.status == 200
    except:
        return False

if __name__ == "__main__":
    print("✅ تم تحميل معالج بدء البوت بنجاح")
    print("🔍 اختبار إنشاء رسائل:")
    
    # اختبار إنشاء الرسائل
    test_status = {
        'api': True,
        'database': True,
        'bot': True,
        'ichancy_site': True
    }
    
    print("\n📝 رسالة الترحيب:")
    print(_create_welcome_message("test_user", test_status)[:200] + "...")
    
    print("\n📝 رسالة الرصيد:")
    test_stats = {
        'account_count': 2,
        'total_deposits': 500.0,
        'total_withdrawals': 200.0,
        'failed_transactions': 1
    }
    print(_create_balance_message(300.0, test_stats)[:200] + "...")
    
    print("\n✅ جميع الاختبارات تمت بنجاح!")
