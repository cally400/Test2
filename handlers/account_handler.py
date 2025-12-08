# handlers/account_handler.py
import re
import random
import string
import logging
import traceback
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from api.ichancy_api import api
from config import config

logger = logging.getLogger(__name__)

class AccountCreationState:
    """حالة إنشاء حساب"""
    def __init__(self):
        self.step = None
        self.username = None
        self.password = None
        self.amount = None

# تخزين حالات المستخدمين
user_states = {}

async def create_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية إنشاء حساب جديد"""
    
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or user_id
    
    logger.info(f"🆕 بدء إنشاء حساب جديد للمستخدم: {user_id}")
    
    try:
        # التحقق من وجود حساب بالفعل
        existing_account = db.get_ichancy_account(user_id)
        if existing_account:
            logger.warning(f"⚠️ المستخدم {user_id} لديه حساب بالفعل: {existing_account['login']}")
            
            await update.message.reply_text(
                f"⚠️ *لديك حساب بالفعل!*\n\n"
                f"👤 *اسم المستخدم:* `{existing_account['login']}`\n"
                f"📧 *الإيميل:* `{existing_account['email']}`\n"
                f"💰 *الرصيد الحالي:* `{existing_account['current_balance']}` NSP\n\n"
                f"إذا كنت تريد إنشاء حساب جديد، يجب أولاً إلغاء تفعيل الحساب الحالي.",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من إعدادات API
        if not all([config.AGENT_USERNAME, config.AGENT_PASSWORD, config.PARENT_ID]):
            logger.error(f"❌ إعدادات API غير مكتملة للمستخدم {user_id}")
            
            await update.message.reply_text(
                "❌ *خدمة إنشاء الحسابات غير متاحة حالياً*\n\n"
                "⚠️ سبب الخطأ: إعدادات واجهة برمجة التطبيقات غير مكتملة.\n"
                "📞 يرجى الاتصال بالدعم الفني: @TSA_Support\n\n"
                "🔧 كود الخطأ: `API_CONFIG_MISSING`",
                parse_mode='Markdown'
            )
            return
        
        # تهيئة حالة المستخدم
        user_states[user_id] = AccountCreationState()
        user_states[user_id].step = 'username'
        
        # طلب اسم المستخدم
        instruction_text = """
*🆕 إنشاء حساب جديد على Ichancy*

🔸 *الخطوة 1: إدخال اسم المستخدم*

📝 *المتطلبات:*
• استخدام الأحرف اللاتينية فقط (A-Z, a-z)
• يمكن استخدام الأرقام (0-9)
• يمكن استخدام النقاط والشرطات (._-)
• الطول: 3-20 حرفاً

💡 *أمثلة صحيحة:*
• `john_doe`
• `ahmed2024`
• `user.tsa`
• `player_one`

❌ *أمثلة خاطئة:*
• `عمر_علي` (أحرف عربية)
• `user@name` (رموز غير مسموحة)
• `ab` (قصير جداً)

✍️ *الرجاء إدخال اسم المستخدم الذي تريده:*
        """
        
        await update.message.reply_text(
            instruction_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')
            ]])
        )
        
        logger.info(f"✅ بدأت عملية إنشاء حساب للمستخدم {user_id}")
        
        # تسجيل بدء العملية
        db.add_transaction({
            'user_id': user_id,
            'type': 'account_creation_started',
            'amount': 0,
            'status': 'pending',
            'details': 'بدأ عملية إنشاء حساب جديد'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل بدء عملية إنشاء حساب للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='account_creation_start_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.account_handler.create_account_handler'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ غير متوقع!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم الفني: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_START_FAIL`",
            parse_mode='Markdown'
        )

async def handle_username_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال اسم المستخدم"""
    
    user_id = str(update.effective_user.id)
    username_input = update.message.text.strip()
    
    logger.info(f"📝 استقبال اسم مستخدم من {user_id}: {username_input}")
    
    try:
        # التحقق من وجود حالة المستخدم
        if user_id not in user_states or user_states[user_id].step != 'username':
            logger.warning(f"⚠️ حالة غير متوقعة للمستخدم {user_id}")
            await update.message.reply_text(
                "❌ *جلسة منتهية!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من صحة اسم المستخدم
        validation_result = _validate_username(username_input)
        
        if not validation_result['valid']:
            logger.warning(f"❌ اسم مستخدم غير صالح من {user_id}: {validation_result['error']}")
            
            await update.message.reply_text(
                f"❌ *اسم مستخدم غير صالح!*\n\n"
                f"⚠️ {validation_result['error']}\n\n"
                f"💡 {validation_result['suggestion']}\n\n"
                f"✍️ الرجاء إدخال اسم مستخدم صحيح:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')
                ]])
            )
            return
        
        # إضافة لاحقة TSA
        base_login = f"{username_input}_TSA"
        
        # التحقق من تفرد الاسم
        uniqueness_result = await _check_username_uniqueness(base_login)
        
        if not uniqueness_result['available']:
            logger.info(f"🔍 اسم {base_login} غير متاح للمستخدم {user_id}")
            
            # محاولة إنشاء اسم بديل
            alternative_login = await _generate_alternative_username(base_login)
            
            user_states[user_id].username = alternative_login
            
            await update.message.reply_text(
                f"⚠️ *الاسم مأخوذ!*\n\n"
                f"اسم المستخدم `{base_login}` موجود بالفعل.\n\n"
                f"✅ *الاسم المقترح:* `{alternative_login}`\n\n"
                f"💡 يمكنك:\n"
                f"1. الموافقة على الاسم المقترح (اضغط 'نعم')\n"
                f"2. إدخال اسم آخر (اضغط 'لا')",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ نعم، استخدم هذا الاسم", callback_data='use_suggested_name'),
                        InlineKeyboardButton("❌ لا، أريد اسم آخر", callback_data='enter_new_name')
                    ],
                    [InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')]
                ])
            )
            return
        
        # حفظ اسم المستخدم
        user_states[user_id].username = base_login
        user_states[user_id].step = 'password'
        
        logger.info(f"✅ اسم مستخدم مقبول للمستخدم {user_id}: {base_login}")
        
        # طلب كلمة المرور
        password_instruction = """
🔸 *الخطوة 2: إدخال كلمة المرور*

🔐 *المتطلبات:*
• الطول: 8-11 حرفاً
• يمكن أن تحتوي على:
  - أحرف لاتينية (A-Z, a-z)
  - أرقام (0-9)
  - رموز خاصة (@#$%^&*)

🚫 *غير مسموح:*
• المسافات
• الأحرف العربية
• الرموز غير الشائعة

🛡️ *نصائح الأمان:*
• لا تستخدم كلمات مرور سهلة التخمين
• اجمع بين أحرف وأرقام ورموز
• لا تستخدم نفس كلمة المرور لحسابات أخرى

🔑 *أمثلة جيدة:*
• `Secure@2024`
• `MyP@ssw0rd!`
• `TSA_Agent#1`

✍️ *الرجاء إدخال كلمة المرور:*
        """
        
        await update.message.reply_text(
            password_instruction,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')
            ]])
        )
        
        # تسجيل تقدم العملية
        db.add_transaction({
            'user_id': user_id,
            'type': 'username_accepted',
            'amount': 0,
            'status': 'success',
            'details': f'اسم المستخدم المقبول: {base_login}'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة اسم المستخدم للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='username_processing_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.account_handler.handle_username_input'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ في معالجة اسم المستخدم!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_USERNAME_FAIL`",
            parse_mode='Markdown'
        )

async def handle_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال كلمة المرور"""
    
    user_id = str(update.effective_user.id)
    password_input = update.message.text.strip()
    
    logger.info(f"🔐 استقبال كلمة مرور من المستخدم {user_id}")
    
    try:
        # التحقق من وجود حالة المستخدم
        if user_id not in user_states or user_states[user_id].step != 'password':
            logger.warning(f"⚠️ حالة غير متوقعة للمستخدم {user_id}")
            await update.message.reply_text(
                "❌ *جلسة منتهية!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من صحة كلمة المرور
        validation_result = _validate_password(password_input)
        
        if not validation_result['valid']:
            logger.warning(f"❌ كلمة مرور غير صالحة من {user_id}: {validation_result['error']}")
            
            await update.message.reply_text(
                f"❌ *كلمة مرور غير صالحة!*\n\n"
                f"⚠️ {validation_result['error']}\n\n"
                f"💡 {validation_result['suggestion']}\n\n"
                f"🔑 الرجاء إدخال كلمة مرور صحيحة:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')
                ]])
            )
            return
        
        # حفظ كلمة المرور
        user_states[user_id].password = password_input
        user_states[user_id].step = 'amount'
        
        logger.info(f"✅ كلمة مرور مقبولة للمستخدم {user_id}")
        
        # طلب مبلغ الشحن الابتدائي
        amount_instruction = f"""
🔸 *الخطوة 3: إدخال مبلغ الشحن الابتدائي*

💰 *المتطلبات:*
• الحد الأدنى: `{config.APP_CONFIG['min_amount']}` NSP
• لا يوجد حد أقصى
• سيتم خصم المبلغ من رصيدك المحلي

📊 *معلومات رصيدك الحالي:*
• الرصيد المتاح: `{db.get_user_balance(user_id):.2f}` NSP

💡 *اقتراحات:*
• `{config.APP_CONFIG['min_amount']}` NSP - الحد الأدنى
• `50` NSP - مبلغ معقول
• `100` NSP - رصيد جيد للبداية

⚠️ *ملاحظة:*
بعد إتمام العملية، سيتم خصم هذا المبلغ من رصيدك المحلي
وإضافته إلى حسابك الجديد على Ichancy.

✍️ *الرجاء إدخال المبلغ المطلوب (بالأرقام فقط):*
        """
        
        await update.message.reply_text(
            amount_instruction,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')
            ]])
        )
        
        # تسجيل تقدم العملية
        db.add_transaction({
            'user_id': user_id,
            'type': 'password_accepted',
            'amount': 0,
            'status': 'success',
            'details': 'كلمة المرور مقبولة'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة كلمة المرور للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='password_processing_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.account_handler.handle_password_input'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ في معالجة كلمة المرور!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_PASSWORD_FAIL`",
            parse_mode='Markdown'
        )

async def handle_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال المبلغ"""
    
    user_id = str(update.effective_user.id)
    amount_input = update.message.text.strip()
    
    logger.info(f"💰 استقبال مبلغ من المستخدم {user_id}: {amount_input}")
    
    try:
        # التحقق من وجود حالة المستخدم
        if user_id not in user_states or user_states[user_id].step != 'amount':
            logger.warning(f"⚠️ حالة غير متوقعة للمستخدم {user_id}")
            await update.message.reply_text(
                "❌ *جلسة منتهية!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من صحة المبلغ
        validation_result = _validate_amount(amount_input, user_id)
        
        if not validation_result['valid']:
            logger.warning(f"❌ مبلغ غير صالح من {user_id}: {validation_result['error']}")
            
            await update.message.reply_text(
                f"❌ *مبلغ غير صالح!*\n\n"
                f"⚠️ {validation_result['error']}\n\n"
                f"💡 {validation_result['suggestion']}\n\n"
                f"💰 الرجاء إدخال مبلغ صحيح:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')
                ]])
            )
            return
        
        # حفظ المبلغ
        amount = validation_result['amount']
        user_states[user_id].amount = amount
        
        logger.info(f"✅ مبلغ مقبول للمستخدم {user_id}: {amount} NSP")
        
        # عرض تأكيد النهائي
        confirmation_text = f"""
✅ *جميع البيانات جاهزة!*

📋 *ملخص البيانات:*

👤 *اسم المستخدم:* `{user_states[user_id].username}`
🔐 *كلمة المرور:* `{user_states[user_id].password}`
💰 *مبلغ الشحن:* `{amount}` NSP

📧 *الإيميل التقديري:* `{user_states[user_id].username}@TSA.com`

⚠️ *تحذيرات هامة:*
1. تأكد من حفظ البيانات في مكان آمن
2. لا تشارك كلمة المرور مع أي شخص
3. عملية الإنشاء قد تستغرق 1-2 دقيقة
4. لا تغلق البوت أثناء العملية

💡 *ملاحظات:*
• بعد الإنشاء، سيتم خصم `{amount}` NSP من رصيدك
• يمكنك تعبئة الرصيد لاحقاً بأي مبلغ
• للدعم: @TSA_Support

❓ *هل تريد متابعة إنشاء الحساب؟*
        """
        
        await update.message.reply_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ نعم، إنشاء الحساب", callback_data='confirm_creation'),
                    InlineKeyboardButton("❌ لا، إلغاء العملية", callback_data='cancel_creation')
                ]
            ])
        )
        
        # تسجيل تقدم العملية
        db.add_transaction({
            'user_id': user_id,
            'type': 'amount_accepted',
            'amount': amount,
            'status': 'pending',
            'details': f'مبلغ الشحن المقبول: {amount} NSP'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة المبلغ للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='amount_processing_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.account_handler.handle_amount_input'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ في معالجة المبلغ!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_AMOUNT_FAIL`",
            parse_mode='Markdown'
        )

async def confirm_account_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد وإنشاء الحساب"""
    
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    chat_id = query.message.chat.id
    
    logger.info(f"✅ تأكيد إنشاء حساب من المستخدم {user_id}")
    
    try:
        # التحقق من وجود جميع البيانات
        if user_id not in user_states or not all([
            user_states[user_id].username,
            user_states[user_id].password,
            user_states[user_id].amount
        ]):
            logger.error(f"❌ بيانات غير مكتملة للمستخدم {user_id}")
            
            await query.edit_message_text(
                "❌ *بيانات غير مكتملة!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        username = user_states[user_id].username
        password = user_states[user_id].password
        amount = user_states[user_id].amount
        
        # تحديث الرسالة للإشارة إلى بدء العملية
        await query.edit_message_text(
            f"⏳ *جارٍ إنشاء الحساب...*\n\n"
            f"👤 المستخدم: `{username}`\n"
            f"💰 المبلغ: `{amount}` NSP\n\n"
            f"⏱️ قد تستغرق العملية 1-2 دقيقة\n"
            f"⚡ يرجى الانتظار...",
            parse_mode='Markdown'
        )
        
        # تسجيل بدء إنشاء الحساب
        db.add_transaction({
            'user_id': user_id,
            'type': 'account_creation_processing',
            'amount': amount,
            'status': 'processing',
            'details': f'بدء إنشاء حساب: {username}'
        })
        
        # 1. خصم المبلغ من رصيد المستخدم المحلي أولاً
        deduction_success = db.update_user_balance(user_id, amount, "subtract")
        
        if not deduction_success:
            error_msg = f"❌ رصيد غير كافي للمستخدم {user_id}"
            logger.error(error_msg)
            
            await query.edit_message_text(
                f"❌ *رصيد غير كافي!*\n\n"
                f"⚠️ رصيدك الحالي غير كافي لخصم `{amount}` NSP\n\n"
                f"📊 رصيدك الحالي: `{db.get_user_balance(user_id):.2f}` NSP\n"
                f"💡 يمكنك تعبئة الرصيد أولاً ثم المحاولة مرة أخرى",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'type': 'account_creation_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': 'رصيد غير كافي'
            })
            
            # تنظيف حالة المستخدم
            del user_states[user_id]
            return
        
        logger.info(f"✅ تم خصم {amount} NSP من رصيد المستخدم {user_id}")
        
        # 2. إنشاء الحساب على Ichancy
        creation_result = api.create_player(username, password)
        
        if not creation_result.get('success'):
            error_msg = creation_result.get('error', 'فشل غير معروف')
            logger.error(f"❌ فشل إنشاء حساب على Ichancy للمستخدم {user_id}: {error_msg}")
            
            # إعادة المبلغ المخصوم
            db.update_user_balance(user_id, amount, "add")
            
            await query.edit_message_text(
                f"❌ *فشل إنشاء الحساب على Ichancy!*\n\n"
                f"⚠️ {error_msg}\n\n"
                f"🔙 تم إعادة `{amount}` NSP إلى رصيدك\n"
                f"📞 للدعم: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_ICHANCY_FAIL`",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'type': 'account_creation_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': f'فشل إنشاء على Ichancy: {error_msg}'
            })
            
            # تنظيف حالة المستخدم
            del user_states[user_id]
            return
        
        player_id = creation_result.get('player_id')
        email = creation_result.get('email', f"{username}@TSA.com")
        
        logger.info(f"✅ تم إنشاء حساب Ichancy للمستخدم {user_id}: {player_id}")
        
        # 3. إيداع المبلغ الابتدائي
        deposit_result = api.deposit(player_id, amount)
        
        if not deposit_result.get('success'):
            error_msg = deposit_result.get('error', 'فشل غير معروف')
            logger.warning(f"⚠️ فشل إيداع المبلغ الابتدائي للمستخدم {user_id}: {error_msg}")
            
            # الحساب أنشئ ولكن الإيداع فشل
            deposit_error_msg = f"تم إنشاء الحساب ولكن فشل الإيداع: {error_msg}"
            
        else:
            deposit_error_msg = None
            logger.info(f"✅ تم إيداع {amount} NSP لحساب {player_id}")
        
        # 4. حفظ الحساب في قاعدة البيانات
        account_data = {
            'user_id': user_id,
            'player_id': player_id,
            'login': username,
            'password': password,
            'email': email,
            'initial_balance': amount
        }
        
        db_success = db.add_ichancy_account(account_data)
        
        if not db_success:
            logger.error(f"❌ فشل حفظ الحساب في قاعدة البيانات للمستخدم {user_id}")
            # نستمر لأن الحساب أنشئ على Ichancy
        
        # 5. جلب الرصيد النهائي
        balance_result = api.get_balance(player_id)
        final_balance = balance_result.get('balance', amount) if balance_result.get('success') else amount
        
        # 6. إرسال رسالة النجاح
        success_message = f"""
🎉 *تم إنشاء الحساب بنجاح!*

✅ *تفاصيل الحساب:*

👤 *اسم المستخدم:* `{username}`
📧 *الإيميل:* `{email}`
🔑 *كلمة المرور:* `{password}`
🆔 *رقم اللاعب:* `{player_id}`
💰 *المبلغ المضاف:* `{amount}` NSP
📊 *الرصيد الحالي:* `{final_balance}` NSP

{f"⚠️ *ملاحظة:* {deposit_error_msg}" if deposit_error_msg else ""}

🛡️ *تعليمات الأمان:*
1. احفظ هذه البيانات في مكان آمن
2. لا تشارك كلمة المرور مع أي أحد
3. يمكنك تغيير كلمة المرور من لوحة اللاعب
4. للدعم: @TSA_Support

💡 *ماذا بعد؟*
• يمكنك تعبئة رصيد إضافي
• يمكنك سحب الرصيد عند الحاجة
• راجع حسابك من "حسابي"
        """
        
        keyboard = [
            [
                InlineKeyboardButton("👤 عرض حسابي", callback_data='my_account'),
                InlineKeyboardButton("💰 تعبئة رصيد", callback_data='deposit')
            ],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            success_message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # 7. تسجيل النجاح
        transaction_details = f'تم إنشاء حساب: {username} (ID: {player_id})'
        if deposit_error_msg:
            transaction_details += f' - {deposit_error_msg}'
        
        db.add_transaction({
            'user_id': user_id,
            'player_id': player_id,
            'type': 'account_creation',
            'amount': amount,
            'status': 'success' if not deposit_error_msg else 'partial_success',
            'error_message': deposit_error_msg,
            'details': transaction_details
        })
        
        # تحديث رصيد الحساب في قاعدة البيانات
        db.update_account_balance(player_id, final_balance)
        
        logger.info(f"✅ تم إنشاء حساب كامل للمستخدم {user_id}: {username}")
        
        # 8. تنظيف حالة المستخدم
        del user_states[user_id]
        
    except Exception as e:
        error_msg = f"❌ فشل إنشاء الحساب للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='account_creation_final_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.account_handler.confirm_account_creation'
        )
        
        try:
            # محاولة إعادة المبلغ إذا فشلت العملية
            try:
                db.update_user_balance(user_id, user_states[user_id].amount, "add")
                refund_msg = f"تم إعادة المبلغ ({user_states[user_id].amount} NSP) إلى رصيدك."
            except:
                refund_msg = "يرجى الاتصال بالدعم لاسترداد المبلغ."
            
            await query.edit_message_text(
                f"❌ *حدث خطأ غير متوقع!*\n\n"
                f"⚠️ {str(e)}\n\n"
                f"🔙 {refund_msg}\n"
                f"📞 للدعم الفوري: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_FINAL_FAIL`",
                parse_mode='Markdown'
            )
            
        except:
            pass
        
        # تنظيف حالة المستخدم في جميع الأحوال
        if user_id in user_states:
            del user_states[user_id]

# ========== دوال التحقق ==========

def _validate_username(username: str) -> Dict:
    """التحقق من صحة اسم المستخدم"""
    
    # التحقق من الطول
    if len(username) < 3:
        return {
            'valid': False,
            'error': 'اسم المستخدم قصير جداً (أقل من 3 أحرف)',
            'suggestion': 'الرجاء استخدام اسم أطول (3-20 حرفاً)'
        }
    
    if len(username) > 20:
        return {
            'valid': False,
            'error': 'اسم المستخدم طويل جداً (أكثر من 20 حرفاً)',
            'suggestion': 'الرجاء استخدام اسم أقصر (3-20 حرفاً)'
        }
    
    # التحقق من الأحرف المسموحة
    if not re.match(r'^[A-Za-z0-9._-]+$', username):
        return {
            'valid': False,
            'error': 'يحتوي على أحرف غير مسموحة',
            'suggestion': 'استخدم الأحرف اللاتينية والأرقام والنقاط والشرطات فقط'
        }
    
    # التحقق من أن يبدأ بحرف
    if not username[0].isalpha():
        return {
            'valid': False,
            'error': 'يجب أن يبدأ اسم المستخدم بحرف',
            'suggestion': 'ابدأ اسم المستخدم بحرف لاتيني'
        }
    
    return {'valid': True, 'error': None, 'suggestion': None}

def _validate_password(password: str) -> Dict:
    """التحقق من صحة كلمة المرور"""
    
    # التحقق من الطول
    min_len = config.APP_CONFIG['min_password_length']
    max_len = config.APP_CONFIG['max_password_length']
    
    if len(password) < min_len:
        return {
            'valid': False,
            'error': f'كلمة المرور قصيرة جداً (أقل من {min_len} أحرف)',
            'suggestion': f'استخدم كلمة مرور بين {min_len} و {max_len} حرفاً'
        }
    
    if len(password) > max_len:
        return {
            'valid': False,
            'error': f'كلمة المرور طويلة جداً (أكثر من {max_len} أحرف)',
            'suggestion': f'استخدم كلمة مرور بين {min_len} و {max_len} حرفاً'
        }
    
    # التحقق من الأحرف المسموحة
    if not re.match(r'^[A-Za-z0-9@#$%^&*]+$', password):
        return {
            'valid': False,
            'error': 'يحتوي على أحرف غير مسموحة',
            'suggestion': 'استخدم الأحرف اللاتينية والأرقام والرموز (@#$%^&*) فقط'
        }
    
    # التحقق من وجود حرف واحد على الأقل
    if not any(c.isalpha() for c in password):
        return {
            'valid': False,
            'error': 'يجب أن تحتوي على حرف واحد على الأقل',
            'suggestion': 'أضف حرفاً لاتينياً إلى كلمة المرور'
        }
    
    return {'valid': True, 'error': None, 'suggestion': None}

def _validate_amount(amount_str: str, user_id: str) -> Dict:
    """التحقق من صحة المبلغ"""
    
    try:
        amount = float(amount_str)
        
        # التحقق من أن المبلغ رقم موجب
        if amount <= 0:
            return {
                'valid': False,
                'error': 'المبلغ يجب أن يكون أكبر من صفر',
                'suggestion': 'أدخل مبلغاً صحيحاً أكبر من الصفر',
                'amount': None
            }
        
        # التحقق من الحد الأدنى
        min_amount = config.APP_CONFIG['min_amount']
        if amount < min_amount:
            return {
                'valid': False,
                'error': f'المبلغ أقل من الحد الأدنى ({min_amount} NSP)',
                'suggestion': f'أدخل مبلغاً يساوي أو أكبر من {min_amount} NSP',
                'amount': None
            }
        
        # التحقق من رصيد المستخدم
        user_balance = db.get_user_balance(user_id)
        if amount > user_balance:
            return {
                'valid': False,
                'error': f'رصيدك غير كافي ({user_balance:.2f} NSP)',
                'suggestion': f'اختر مبلغاً أقل من أو يساوي {user_balance:.2f} NSP، أو قم بتعبئة الرصيد',
                'amount': None
            }
        
        # تقريب المبلغ إلى منزلتين عشريتين
        amount = round(amount, 2)
        
        return {
            'valid': True,
            'error': None,
            'suggestion': None,
            'amount': amount
        }
        
    except ValueError:
        return {
            'valid': False,
            'error': 'المبلغ غير صالح',
            'suggestion': 'أدخل رقماً صحيحاً (مثال: 50، 100.5)',
            'amount': None
        }

async def _check_username_uniqueness(username: str) -> Dict:
    """التحقق من تفرد اسم المستخدم"""
    
    try:
        # التحقق من قاعدة البيانات المحلية
        existing_logins = db.get_all_ichancy_logins()
        if username in existing_logins:
            return {'available': False, 'reason': 'موجود في قاعدة البيانات المحلية'}
        
        # التحقق من Ichancy API
        exists_on_ichancy = api.check_player_exists(username)
        if exists_on_ichancy:
            return {'available': False, 'reason': 'موجود على Ichancy'}
        
        return {'available': True, 'reason': None}
        
    except Exception as e:
        logger.error(f"❌ فشل التحقق من تفرد اسم المستخدم {username}: {str(e)}")
        # نفترض أنه غير متاح في حالة الخطأ لتجنب التضارب
        return {'available': False, 'reason': f'خطأ في التحقق: {str(e)}'}

async def _generate_alternative_username(base_username: str) -> str:
    """إنشاء اسم مستخدم بديل"""
    
    # محاولة إضافة أرقام
    for i in range(1, 100):
        alternative = f"{base_username}{i}"
        
        # التحقق من التوفر
        check_result = await _check_username_uniqueness(alternative)
        if check_result['available']:
            return alternative
    
    # إذا فشلت جميع المحاولات، أضف سلسلة عشوائية
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{base_username}_{random_suffix}"

async def cancel_account_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء عملية إنشاء الحساب"""
    
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    logger.info(f"❌ إلغاء إنشاء حساب من المستخدم {user_id}")
    
    # تنظيف حالة المستخدم
    if user_id in user_states:
        del user_states[user_id]
    
    await query.edit_message_text(
        "❌ *تم إلغاء عملية إنشاء الحساب*\n\n"
        "يمكنك البدء من جديد باستخدام /start",
        parse_mode='Markdown'
    )
    
    # تسجيل الإلغاء
    db.add_transaction({
        'user_id': user_id,
        'type': 'account_creation_cancelled',
        'amount': 0,
        'status': 'cancelled',
        'details': 'ألغى المستخدم عملية إنشاء الحساب'
    })

if __name__ == "__main__":
    print("✅ تم تحميل معالج إنشاء الحسابات بنجاح")
    print("🔍 اختبار دوال التحقق:")
    
    # اختبار التحقق من اسم المستخدم
    test_usernames = ["john", "john_doe", "123user", "user@name", "ab"]
    for username in test_usernames:
        result = _validate_username(username)
        print(f"📝 {username}: {'✅' if result['valid'] else '❌'} {result.get('error', '')}")
    
    # اختبار التحقق من كلمة المرور
    test_passwords = ["pass", "password123", "Secure@2024", "short", "verylongpassword123"]
    for password in test_passwords:
        result = _validate_password(password)
        print(f"🔐 {password}: {'✅' if result['valid'] else '❌'} {result.get('error', '')}")
    
    print("\n✅ جميع الاختبارات تمت بنجاح!")
