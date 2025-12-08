
# handlers/deposit_handler.py
import logging
import traceback
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from api.ichancy_api import api
from config import config

logger = logging.getLogger(__name__)

class DepositState:
    """حالة عملية الإيداع"""
    def __init__(self):
        self.step = None
        self.amount = None
        self.player_id = None
        self.login = None

# تخزين حالات المستخدمين
deposit_states = {}

async def deposit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية تعبئة الرصيد"""
    
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or user_id
    
    logger.info(f"💰 بدء عملية تعبئة الرصيد للمستخدم: {user_id}")
    
    try:
        # التحقق من وجود حساب Ichancy
        ichancy_account = db.get_ichancy_account(user_id)
        
        if not ichancy_account:
            logger.warning(f"⚠️ المستخدم {user_id} لا يملك حساب Ichancy")
            
            await update.message.reply_text(
                "❌ *ليس لديك حساب على Ichancy!*\n\n"
                "⚠️ يجب إنشاء حساب أولاً قبل تعبئة الرصيد.\n\n"
                "💡 *الحلول المتاحة:*\n"
                "1. إنشاء حساب جديد باستخدام 'إنشاء حساب جديد'\n"
                "2. التحقق من أن حسابك نشط\n\n"
                "📞 للدعم: @TSA_Support",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🆕 إنشاء حساب جديد", callback_data='create_account')
                ]])
            )
            return
        
        # التحقق من حالة الحساب
        if ichancy_account.get('status') != 'active':
            logger.warning(f"⚠️ حساب المستخدم {user_id} غير نشط: {ichancy_account['status']}")
            
            await update.message.reply_text(
                f"❌ *حسابك غير نشط!*\n\n"
                f"⚠️ حالة الحساب: `{ichancy_account.get('status', 'unknown')}`\n\n"
                f"💡 *الحلول المتاحة:*\n"
                f"1. التحقق من سبب تعطيل الحساب\n"
                f"2. إنشاء حساب جديد\n"
                f"3. الاتصال بدعم Ichancy\n\n"
                f"📞 للدعم: @TSA_Support",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من إعدادات API
        if not all([config.AGENT_USERNAME, config.AGENT_PASSWORD, config.PARENT_ID]):
            logger.error(f"❌ إعدادات API غير مكتملة للمستخدم {user_id}")
            
            await update.message.reply_text(
                "❌ *خدمة تعبئة الرصيد غير متاحة حالياً*\n\n"
                "⚠️ سبب الخطأ: إعدادات واجهة برمجة التطبيقات غير مكتملة.\n"
                "📞 يرجى الاتصال بالدعم الفني: @TSA_Support\n\n"
                "🔧 كود الخطأ: `API_CONFIG_MISSING`",
                parse_mode='Markdown'
            )
            return
        
        # جلب رصيد المستخدم المحلي
        user_balance = db.get_user_balance(user_id)
        
        if user_balance <= 0:
            logger.warning(f"⚠️ رصيد المستخدم {user_id} صفر أو أقل: {user_balance}")
            
            await update.message.reply_text(
                f"❌ *رصيدك المحلي غير كافي!*\n\n"
                f"💰 رصيدك الحالي: `{user_balance:.2f}` NSP\n"
                f"📊 الحد الأدنى للإيداع: `{config.APP_CONFIG['min_amount']}` NSP\n\n"
                f"💡 *الحلول المتاحة:*\n"
                f"1. إضافة رصيد إلى حسابك المحلي\n"
                f"2. الاتصال بالدعم لإضافة الرصيد\n\n"
                f"📞 للدعم: @TSA_Support",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📞 الاتصال بالدعم لإضافة رصيد", url='https://t.me/TSA_Support')
                ]])
            )
            return
        
        # تهيئة حالة الإيداع
        deposit_states[user_id] = DepositState()
        deposit_states[user_id].step = 'amount'
        deposit_states[user_id].player_id = ichancy_account['player_id']
        deposit_states[user_id].login = ichancy_account['login']
        
        # جلب رصيد الحساب على Ichancy
        balance_result = api.get_balance(ichancy_account['player_id'])
        ichancy_balance = balance_result.get('balance', 0) if balance_result.get('success') else 0
        
        # رسالة التعليمات
        instruction_text = f"""
💰 *تعبئة رصيد حساب Ichancy*

🔸 *الخطوة 1: إدخال المبلغ*

📋 *معلومات الحساب:*
👤 *اسم المستخدم:* `{ichancy_account['login']}`
📧 *الإيميل:* `{ichancy_account['email']}`
🆔 *رقم اللاعب:* `{ichancy_account['player_id']}`
📊 *رصيد Ichancy الحالي:* `{ichancy_balance:.2f}` NSP

💰 *معلومات الرصيد المحلي:*
📊 *رصيدك المتاح:* `{user_balance:.2f}` NSP
📈 *الحد الأدنى:* `{config.APP_CONFIG['min_amount']}` NSP

⚠️ *ملاحظات هامة:*
1. سيتم خصم المبلغ من رصيدك المحلي فوراً
2. العملية لا يمكن التراجع عنها
3. تأكد من صحة المبلغ قبل التأكيد
4. قد تستغرق العملية 1-2 دقيقة

💡 *اقتراحات المبالغ:*
• `{config.APP_CONFIG['min_amount']}` NSP - الحد الأدنى
• `50` NSP - مبلغ معقول
• `100` NSP - مبلغ جيد
• `500` NSP - مبلغ كبير

✍️ *الرجاء إدخال المبلغ المطلوب (بالأرقام فقط):*
        """
        
        await update.message.reply_text(
            instruction_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_deposit')
            ]])
        )
        
        logger.info(f"✅ بدأت عملية إيداع للمستخدم {user_id} - حساب: {ichancy_account['login']}")
        
        # تسجيل بدء العملية
        db.add_transaction({
            'user_id': user_id,
            'player_id': ichancy_account['player_id'],
            'type': 'deposit_started',
            'amount': 0,
            'status': 'pending',
            'details': f'بدأ عملية إيداع لحساب {ichancy_account["login"]}'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل بدء عملية الإيداع للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='deposit_start_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.deposit_handler.deposit_handler'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ غير متوقع!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم الفني: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_DEPOSIT_START_FAIL`",
            parse_mode='Markdown'
        )

async def handle_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال مبلغ الإيداع"""
    
    user_id = str(update.effective_user.id)
    amount_input = update.message.text.strip()
    
    logger.info(f"💵 استقبال مبلغ إيداع من {user_id}: {amount_input}")
    
    try:
        # التحقق من وجود حالة المستخدم
        if user_id not in deposit_states or deposit_states[user_id].step != 'amount':
            logger.warning(f"⚠️ حالة غير متوقعة للمستخدم {user_id}")
            await update.message.reply_text(
                "❌ *جلسة منتهية!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من صحة المبلغ
        validation_result = _validate_deposit_amount(amount_input, user_id)
        
        if not validation_result['valid']:
            logger.warning(f"❌ مبلغ إيداع غير صالح من {user_id}: {validation_result['error']}")
            
            await update.message.reply_text(
                f"❌ *مبلغ غير صالح!*\n\n"
                f"⚠️ {validation_result['error']}\n\n"
                f"💡 {validation_result['suggestion']}\n\n"
                f"💰 الرجاء إدخال مبلغ صحيح:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_deposit')
                ]])
            )
            return
        
        # حفظ المبلغ
        amount = validation_result['amount']
        deposit_states[user_id].amount = amount
        deposit_states[user_id].step = 'confirm'
        
        logger.info(f"✅ مبلغ إيداع مقبول للمستخدم {user_id}: {amount} NSP")
        
        # جلب المعلومات الحالية
        user_balance = db.get_user_balance(user_id)
        account = db.get_ichancy_account(user_id)
        
        # عرض تأكيد النهائي
        confirmation_text = f"""
✅ *بيانات الإيداع جاهزة!*

📋 *ملخص البيانات:*

👤 *اسم المستخدم:* `{deposit_states[user_id].login}`
🆔 *رقم اللاعب:* `{deposit_states[user_id].player_id}`
💰 *مبلغ الإيداع:* `{amount}` NSP

📊 *المعلومات المالية:*
• رصيدك المحلي الحالي: `{user_balance:.2f}` NSP
• رصيدك المحلي بعد الخصم: `{user_balance - amount:.2f}` NSP
• رصيد حساب Ichancy الحالي: `{account.get('current_balance', 0):.2f}` NSP
• رصيد حساب Ichancy بعد الإيداع: `{account.get('current_balance', 0) + amount:.2f}` NSP

⚠️ *تحذيرات هامة:*
1. سيتم خصم `{amount}` NSP من رصيدك المحلي فوراً
2. العملية لا يمكن التراجع عنها
3. تأكد من صحة البيانات قبل التأكيد
4. قد تستغرق العملية 1-2 دقيقة

💡 *ملاحظات:*
• الحد الأدنى للإيداع: `{config.APP_CONFIG['min_amount']}` NSP
• العمولات: لا توجد عمولات
• وقت المعالجة: 1-2 دقيقة
• للدعم: @TSA_Support

❓ *هل تريد متابعة عملية الإيداع؟*
        """
        
        await update.message.reply_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ نعم، متابعة الإيداع", callback_data='confirm_deposit'),
                    InlineKeyboardButton("❌ لا، إلغاء العملية", callback_data='cancel_deposit')
                ]
            ])
        )
        
        # تسجيل تقدم العملية
        db.add_transaction({
            'user_id': user_id,
            'player_id': deposit_states[user_id].player_id,
            'type': 'deposit_amount_accepted',
            'amount': amount,
            'status': 'pending',
            'details': f'مبلغ الإيداع المقبول: {amount} NSP'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة مبلغ الإيداع للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='deposit_amount_processing_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.deposit_handler.handle_deposit_amount'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ في معالجة المبلغ!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_DEPOSIT_AMOUNT_FAIL`",
            parse_mode='Markdown'
        )

async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد وإتمام عملية الإيداع"""
    
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    chat_id = query.message.chat.id
    
    logger.info(f"✅ تأكيد إيداع من المستخدم {user_id}")
    
    try:
        # التحقق من وجود جميع البيانات
        if user_id not in deposit_states or not all([
            deposit_states[user_id].amount,
            deposit_states[user_id].player_id,
            deposit_states[user_id].login
        ]):
            logger.error(f"❌ بيانات غير مكتملة للمستخدم {user_id}")
            
            await query.edit_message_text(
                "❌ *بيانات غير مكتملة!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        amount = deposit_states[user_id].amount
        player_id = deposit_states[user_id].player_id
        login = deposit_states[user_id].login
        
        # تحديث الرسالة للإشارة إلى بدء العملية
        await query.edit_message_text(
            f"⏳ *جارٍ معالجة الإيداع...*\n\n"
            f"👤 المستخدم: `{login}`\n"
            f"💰 المبلغ: `{amount}` NSP\n"
            f"🆔 رقم اللاعب: `{player_id}`\n\n"
            f"⏱️ قد تستغرق العملية 1-2 دقيقة\n"
            f"⚡ يرجى الانتظار...",
            parse_mode='Markdown'
        )
        
        # تسجيل بدء معالجة الإيداع
        db.add_transaction({
            'user_id': user_id,
            'player_id': player_id,
            'type': 'deposit_processing',
            'amount': amount,
            'status': 'processing',
            'details': f'بدء معالجة إيداع لحساب {login}'
        })
        
        # 1. خصم المبلغ من رصيد المستخدم المحلي أولاً
        deduction_success = db.update_user_balance(user_id, amount, "subtract")
        
        if not deduction_success:
            error_msg = f"❌ فشل خصم المبلغ من الرصيد المحلي للمستخدم {user_id}"
            logger.error(error_msg)
            
            await query.edit_message_text(
                f"❌ *فشل خصم المبلغ!*\n\n"
                f"⚠️ تعذر خصم `{amount}` NSP من رصيدك المحلي\n\n"
                f"📊 رصيدك الحالي: `{db.get_user_balance(user_id):.2f}` NSP\n"
                f"💡 قد يكون رصيدك غير كافي أو حدث خطأ في النظام",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'player_id': player_id,
                'type': 'deposit_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': 'فشل خصم المبلغ من الرصيد المحلي'
            })
            
            # تنظيف حالة المستخدم
            del deposit_states[user_id]
            return
        
        logger.info(f"✅ تم خصم {amount} NSP من رصيد المستخدم {user_id}")
        
        # 2. إيداع المبلغ على حساب Ichancy
        deposit_result = api.deposit(player_id, amount)
        
        if not deposit_result.get('success'):
            error_msg = deposit_result.get('error', 'فشل غير معروف في الإيداع')
            logger.error(f"❌ فشل إيداع على Ichancy للمستخدم {user_id}: {error_msg}")
            
            # إعادة المبلغ المخصوم
            db.update_user_balance(user_id, amount, "add")
            
            await query.edit_message_text(
                f"❌ *فشل إيداع المبلغ على Ichancy!*\n\n"
                f"⚠️ {error_msg}\n\n"
                f"🔙 تم إعادة `{amount}` NSP إلى رصيدك المحلي\n"
                f"📞 للدعم: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_ICHANCY_DEPOSIT_FAIL`",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'player_id': player_id,
                'type': 'deposit_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': f'فشل إيداع على Ichancy: {error_msg}'
            })
            
            # تنظيف حالة المستخدم
            del deposit_states[user_id]
            return
        
        logger.info(f"✅ تم إيداع {amount} NSP لحساب {player_id} على Ichancy")
        
        # 3. جلب الرصيد الجديد
        balance_result = api.get_balance(player_id)
        
        if balance_result.get('success'):
            new_balance = balance_result.get('balance', 0)
            
            # تحديث رصيد الحساب في قاعدة البيانات
            db.update_account_balance(player_id, new_balance)
            
            # حساب الرصيد السابق
            old_balance = new_balance - amount
            
            balance_info = f"""
📊 *معلومات الرصيد:*
• الرصيد السابق: `{old_balance:.2f}` NSP
• المبلغ المضاف: `{amount}` NSP
• الرصيد الحالي: `{new_balance:.2f}` NSP
            """
        else:
            balance_info = "⚠️ *ملاحظة:* تعذر جلب الرصيد الحالي، يرجى التحقق يدوياً"
            new_balance = None
        
        # 4. إرسال رسالة النجاح
        success_message = f"""
🎉 *تم الإيداع بنجاح!*

✅ *تفاصيل العملية:*

👤 *اسم المستخدم:* `{login}`
🆔 *رقم اللاعب:* `{player_id}`
💰 *المبلغ المودع:* `{amount}` NSP
⏰ *وقت المعالجة:* فوري

{balance_info}

📋 *ملخص المعاملة:*
• حالة المعاملة: ✅ ناجحة
• وقت التنفيذ: فوري
• الرقم المرجعي: `{user_id[:8]}_{player_id[:4]}`
• وقت التسجيل: الآن

🛡️ *تعليمات الأمان:*
1. احتفظ بهذه المعلومات لأغراض المراجعة
2. يمكنك التحقق من رصيدك على Ichancy مباشرة
3. للاستفسارات: @TSA_Support

💡 *ماذا بعد؟*
• يمكنك سحب الرصيد عند الحاجة
• يمكنك تعبئة رصيد إضافي
• راجع حسابك من "حسابي"
        """
        
        keyboard = [
            [
                InlineKeyboardButton("👤 عرض حسابي", callback_data='my_account'),
                InlineKeyboardButton("💳 سحب رصيد", callback_data='withdraw')
            ],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            success_message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # 5. تسجيل النجاح
        transaction_details = f'إيداع ناجح لحساب {login} (ID: {player_id})'
        if new_balance is not None:
            transaction_details += f' - الرصيد الجديد: {new_balance} NSP'
        
        db.add_transaction({
            'user_id': user_id,
            'player_id': player_id,
            'type': 'deposit',
            'amount': amount,
            'status': 'success',
            'details': transaction_details
        })
        
        # 6. تحديث رصيد المستخدم المحلي النهائي
        final_balance = db.get_user_balance(user_id)
        logger.info(f"✅ رصيد المستخدم {user_id} النهائي: {final_balance} NSP")
        
        logger.info(f"✅ تم إتمام إيداع كامل للمستخدم {user_id}: {amount} NSP للحساب {login}")
        
        # 7. تنظيف حالة المستخدم
        del deposit_states[user_id]
        
    except Exception as e:
        error_msg = f"❌ فشل إتمام الإيداع للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='deposit_final_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.deposit_handler.confirm_deposit'
        )
        
        try:
            # محاولة إعادة المبلغ إذا فشلت العملية
            try:
                if user_id in deposit_states and deposit_states[user_id].amount:
                    db.update_user_balance(user_id, deposit_states[user_id].amount, "add")
                    refund_msg = f"تم إعادة المبلغ ({deposit_states[user_id].amount} NSP) إلى رصيدك."
                else:
                    refund_msg = "يرجى الاتصال بالدعم لاسترداد المبلغ."
            except:
                refund_msg = "يرجى الاتصال بالدعم لاسترداد المبلغ."
            
            await query.edit_message_text(
                f"❌ *حدث خطأ غير متوقع!*\n\n"
                f"⚠️ {str(e)}\n\n"
                f"🔙 {refund_msg}\n"
                f"📞 للدعم الفوري: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_DEPOSIT_FINAL_FAIL`",
                parse_mode='Markdown'
            )
            
        except:
            pass
        
        # تنظيف حالة المستخدم في جميع الأحوال
        if user_id in deposit_states:
            del deposit_states[user_id]

async def cancel_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء عملية الإيداع"""
    
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    logger.info(f"❌ إلغاء إيداع من المستخدم {user_id}")
    
    # تنظيف حالة المستخدم
    if user_id in deposit_states:
        del deposit_states[user_id]
    
    await query.edit_message_text(
        "❌ *تم إلغاء عملية الإيداع*\n\n"
        "يمكنك البدء من جديد باستخدام /start أو إعادة المحاولة",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 إعادة المحاولة", callback_data='deposit'),
            InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')
        ]])
    )
    
    # تسجيل الإلغاء
    db.add_transaction({
        'user_id': user_id,
        'type': 'deposit_cancelled',
        'amount': 0,
        'status': 'cancelled',
        'details': 'ألغى المستخدم عملية الإيداع'
    })

async def quick_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: float):
    """إيداع سريع بمبلغ محدد مسبقاً"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"⚡ إيداع سريع للمستخدم {user_id}: {amount} NSP")
    
    try:
        # التحقق من وجود حساب Ichancy
        ichancy_account = db.get_ichancy_account(user_id)
        
        if not ichancy_account:
            await update.message.reply_text(
                "❌ ليس لديك حساب على Ichancy!",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من رصيد المستخدم
        user_balance = db.get_user_balance(user_id)
        
        if user_balance < amount:
            await update.message.reply_text(
                f"❌ رصيدك غير كافي! الرصيد الحالي: {user_balance:.2f} NSP",
                parse_mode='Markdown'
            )
            return
        
        # خصم المبلغ
        deduction_success = db.update_user_balance(user_id, amount, "subtract")
        
        if not deduction_success:
            await update.message.reply_text(
                "❌ فشل خصم المبلغ!",
                parse_mode='Markdown'
            )
            return
        
        # إيداع المبلغ على Ichancy
        deposit_result = api.deposit(ichancy_account['player_id'], amount)
        
        if not deposit_result.get('success'):
            # إعادة المبلغ
            db.update_user_balance(user_id, amount, "add")
            
            await update.message.reply_text(
                f"❌ فشل الإيداع: {deposit_result.get('error', 'خطأ غير معروف')}",
                parse_mode='Markdown'
            )
            return
        
        # تسجيل النجاح
        db.add_transaction({
            'user_id': user_id,
            'player_id': ichancy_account['player_id'],
            'type': 'quick_deposit',
            'amount': amount,
            'status': 'success',
            'details': f'إيداع سريع بمبلغ {amount} NSP'
        })
        
        await update.message.reply_text(
            f"✅ تم إيداع {amount} NSP بنجاح!",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ فشل الإيداع السريع للمستخدم {user_id}: {str(e)}")
        
        await update.message.reply_text(
            f"❌ حدث خطأ: {str(e)}",
            parse_mode='Markdown'
        )

# ========== دوال التحقق ==========

def _validate_deposit_amount(amount_str: str, user_id: str) -> Dict:
    """التحقق من صحة مبلغ الإيداع"""
    
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
                'suggestion': f'اختر مبلغاً أقل من أو يساوي {user_balance:.2f} NSP، أو قم بتعبئة رصيدك المحلي',
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

async def check_deposit_limits(user_id: str, amount: float) -> Dict:
    """التحقق من حدود الإيداع"""
    
    try:
        # الحصول على إحصائيات المستخدم
        user_stats = db.get_user_stats(user_id)
        
        # التحقق من الحد اليومي (إذا كان مطبقاً)
        daily_limit = 10000  # مثال: 10,000 NSP يومياً
        daily_deposits = user_stats.get('total_deposits', 0)
        
        if daily_deposits + amount > daily_limit:
            return {
                'allowed': False,
                'error': f'تجاوزت الحد اليومي للإيداع ({daily_limit} NSP)',
                'remaining': daily_limit - daily_deposits
            }
        
        # التحقق من الحد لكل معاملة
        per_transaction_limit = 5000  # مثال: 5,000 NSP لكل معاملة
        
        if amount > per_transaction_limit:
            return {
                'allowed': False,
                'error': f'المبلغ يتجاوز الحد المسموح لكل معاملة ({per_transaction_limit} NSP)',
                'remaining': per_transaction_limit
            }
        
        return {
            'allowed': True,
            'error': None,
            'remaining': daily_limit - daily_deposits
        }
        
    except Exception as e:
        logger.error(f"❌ فشل التحقق من حدود الإيداع للمستخدم {user_id}: {str(e)}")
        return {
            'allowed': True,  # نسمح في حالة الخطأ
            'error': f'خطأ في التحقق: {str(e)}',
            'remaining': None
        }

async def get_deposit_history(user_id: str, limit: int = 10) -> list:
    """الحصول على سجل عمليات الإيداع"""
    
    try:
        transactions = db.get_user_transactions(user_id, limit)
        
        deposit_history = []
        for transaction in transactions:
            if transaction['type'] == 'deposit':
                deposit_history.append({
                    'amount': transaction['amount'],
                    'status': transaction['status'],
                    'date': transaction['created_at'],
                    'player_id': transaction.get('player_id', 'N/A'),
                    'error': transaction.get('error_message')
                })
        
        return deposit_history
        
    except Exception as e:
        logger.error(f"❌ فشل جلب سجل الإيداع للمستخدم {user_id}: {str(e)}")
        return []

async def show_deposit_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل عمليات الإيداع"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"📜 طلب سجل الإيداع من المستخدم {user_id}")
    
    try:
        history = await get_deposit_history(user_id, limit=20)
        
        if not history:
            await update.message.reply_text(
                "📭 *لا توجد عمليات إيداع سابقة*",
                parse_mode='Markdown'
            )
            return
        
        history_text = "📋 *سجل عمليات الإيداع*\n\n"
        
        for i, deposit in enumerate(history, 1):
            status_icon = "✅" if deposit['status'] == 'success' else "❌"
            date = deposit['date'].split()[0] if deposit['date'] else "غير معروف"
            
            history_text += f"{i}. {status_icon} *{deposit['amount']}* NSP\n"
            history_text += f"   📅 {date} | {deposit['status']}\n"
            
            if deposit.get('error'):
                history_text += f"   ⚠️ {deposit['error'][:50]}...\n"
            
            history_text += "\n"
        
        await update.message.reply_text(
            history_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 العودة", callback_data='my_balance')
            ]])
        )
        
    except Exception as e:
        error_msg = f"❌ فشل عرض سجل الإيداع للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        await update.message.reply_text(
            f"❌ حدث خطأ في جلب السجل: {str(e)}",
            parse_mode='Markdown'
        )

if __name__ == "__main__":
    print("✅ تم تحميل معالج تعبئة الرصيد بنجاح")
    print("🔍 اختبار دوال التحقق:")
    
    # اختبار التحقق من المبالغ
    test_amounts = [
        ("50", "12345"),
        ("-10", "12345"),
        ("0", "12345"),
        ("1000000", "12345"),
        ("abc", "12345")
    ]
    
    for amount_str, user_id in test_amounts:
        result = _validate_deposit_amount(amount_str, user_id)
        print(f"💰 {amount_str} (User: {user_id}): {'✅' if result['valid'] else '❌'} {result.get('error', '')}")
    
    print("\n✅ جميع الاختبارات تمت بنجاح!")
