
# handlers/withdraw_handler.py
import logging
import traceback
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from api.ichancy_api import api
from config import config

logger = logging.getLogger(__name__)

class WithdrawState:
    """حالة عملية السحب"""
    def __init__(self):
        self.step = None
        self.amount = None
        self.player_id = None
        self.login = None
        self.current_balance = None

# تخزين حالات المستخدمين
withdraw_states = {}

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية سحب الرصيد"""
    
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or user_id
    
    logger.info(f"💳 بدء عملية سحب الرصيد للمستخدم: {user_id}")
    
    try:
        # التحقق من وجود حساب Ichancy
        ichancy_account = db.get_ichancy_account(user_id)
        
        if not ichancy_account:
            logger.warning(f"⚠️ المستخدم {user_id} لا يملك حساب Ichancy")
            
            await update.message.reply_text(
                "❌ *ليس لديك حساب على Ichancy!*\n\n"
                "⚠️ يجب إنشاء حساب أولاً قبل سحب الرصيد.\n\n"
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
                "❌ *خدمة سحب الرصيد غير متاحة حالياً*\n\n"
                "⚠️ سبب الخطأ: إعدادات واجهة برمجة التطبيقات غير مكتملة.\n"
                "📞 يرجى الاتصال بالدعم الفني: @TSA_Support\n\n"
                "🔧 كود الخطأ: `API_CONFIG_MISSING`",
                parse_mode='Markdown'
            )
            return
        
        # جلب رصيد الحساب على Ichancy
        balance_result = api.get_balance(ichancy_account['player_id'])
        
        if not balance_result.get('success'):
            error_msg = balance_result.get('error', 'فشل غير معروف في جلب الرصيد')
            logger.error(f"❌ فشل جلب رصيد Ichancy للمستخدم {user_id}: {error_msg}")
            
            await update.message.reply_text(
                f"❌ *تعذر جلب رصيد حسابك!*\n\n"
                f"⚠️ {error_msg}\n\n"
                f"💡 *الحلول المتاحة:*\n"
                f"1. حاول مرة أخرى بعد قليل\n"
                f"2. تحقق من اتصال الإنترنت\n"
                f"3. اتصل بالدعم إذا استمر الخطأ\n\n"
                f"📞 للدعم: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_BALANCE_FAIL`",
                parse_mode='Markdown'
            )
            return
        
        current_balance = balance_result.get('balance', 0)
        
        if current_balance <= 0:
            logger.warning(f"⚠️ رصيد Ichancy للمستخدم {user_id} صفر أو أقل: {current_balance}")
            
            await update.message.reply_text(
                f"❌ *رصيد حساب Ichancy غير كافي!*\n\n"
                f"💰 رصيد حسابك الحالي: `{current_balance:.2f}` NSP\n"
                f"📊 الحد الأدنى للسحب: `{config.APP_CONFIG['min_amount']}` NSP\n\n"
                f"💡 *الحلول المتاحة:*\n"
                f"1. قم بتعبئة رصيد حساب Ichancy أولاً\n"
                f"2. انتظر حتى يكون لديك رصيد كافٍ\n\n"
                f"📞 للدعم: @TSA_Support",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💰 تعبئة الرصيد", callback_data='deposit')
                ]])
            )
            return
        
        # تهيئة حالة السحب
        withdraw_states[user_id] = WithdrawState()
        withdraw_states[user_id].step = 'amount'
        withdraw_states[user_id].player_id = ichancy_account['player_id']
        withdraw_states[user_id].login = ichancy_account['login']
        withdraw_states[user_id].current_balance = current_balance
        
        # جلب رصيد المستخدم المحلي
        user_balance = db.get_user_balance(user_id)
        
        # رسالة التعليمات
        instruction_text = f"""
💳 *سحب رصيد من حساب Ichancy*

🔸 *الخطوة 1: إدخال المبلغ*

📋 *معلومات الحساب:*
👤 *اسم المستخدم:* `{ichancy_account['login']}`
📧 *الإيميل:* `{ichancy_account['email']}`
🆔 *رقم اللاعب:* `{ichancy_account['player_id']}`
📊 *رصيد Ichancy الحالي:* `{current_balance:.2f}` NSP

💰 *معلومات الرصيد المحلي:*
📊 *رصيدك المحلي الحالي:* `{user_balance:.2f}` NSP
📊 *رصيدك المحلي بعد السحب:* `{user_balance + min(current_balance, config.APP_CONFIG['min_amount']):.2f}` NSP (تقديري)

⚠️ *ملاحظات هامة:*
1. سيتم إضافة المبلغ إلى رصيدك المحلي فوراً
2. العملية لا يمكن التراجع عنها
3. تأكد من صحة المبلغ قبل التأكيد
4. قد تستغرق العملية 1-2 دقيقة
5. الحد الأدنى للسحب: `{config.APP_CONFIG['min_amount']}` NSP

💡 *اقتراحات المبالغ:*
• `{config.APP_CONFIG['min_amount']}` NSP - الحد الأدنى
• `50` NSP - مبلغ معقول
• `100` NSP - مبلغ جيد
• `{min(500, current_balance)}` NSP - مبلغ كبير (حسب الرصيد)

✍️ *الرجاء إدخال المبلغ المطلوب (بالأرقام فقط):*
        """
        
        await update.message.reply_text(
            instruction_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_withdraw')
            ]])
        )
        
        logger.info(f"✅ بدأت عملية سحب للمستخدم {user_id} - حساب: {ichancy_account['login']} - الرصيد: {current_balance}")
        
        # تسجيل بدء العملية
        db.add_transaction({
            'user_id': user_id,
            'player_id': ichancy_account['player_id'],
            'type': 'withdraw_started',
            'amount': 0,
            'status': 'pending',
            'details': f'بدأ عملية سحب من حساب {ichancy_account["login"]} - الرصيد: {current_balance}'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل بدء عملية السحب للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='withdraw_start_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.withdraw_handler.withdraw_handler'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ غير متوقع!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم الفني: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_WITHDRAW_START_FAIL`",
            parse_mode='Markdown'
        )

async def handle_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إدخال مبلغ السحب"""
    
    user_id = str(update.effective_user.id)
    amount_input = update.message.text.strip()
    
    logger.info(f"💵 استقبال مبلغ سحب من {user_id}: {amount_input}")
    
    try:
        # التحقق من وجود حالة المستخدم
        if user_id not in withdraw_states or withdraw_states[user_id].step != 'amount':
            logger.warning(f"⚠️ حالة غير متوقعة للمستخدم {user_id}")
            await update.message.reply_text(
                "❌ *جلسة منتهية!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من صحة المبلغ
        validation_result = _validate_withdraw_amount(
            amount_input, 
            user_id, 
            withdraw_states[user_id].current_balance
        )
        
        if not validation_result['valid']:
            logger.warning(f"❌ مبلغ سحب غير صالح من {user_id}: {validation_result['error']}")
            
            await update.message.reply_text(
                f"❌ *مبلغ غير صالح!*\n\n"
                f"⚠️ {validation_result['error']}\n\n"
                f"💡 {validation_result['suggestion']}\n\n"
                f"💰 الرجاء إدخال مبلغ صحيح:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_withdraw')
                ]])
            )
            return
        
        # حفظ المبلغ
        amount = validation_result['amount']
        withdraw_states[user_id].amount = amount
        withdraw_states[user_id].step = 'confirm'
        
        logger.info(f"✅ مبلغ سحب مقبول للمستخدم {user_id}: {amount} NSP")
        
        # جلب المعلومات الحالية
        user_balance = db.get_user_balance(user_id)
        current_balance = withdraw_states[user_id].current_balance
        
        # التحقق من حدود السحب
        limits_check = await check_withdraw_limits(user_id, amount)
        
        if not limits_check['allowed']:
            error_msg = f"❌ {limits_check['error']}"
            logger.warning(f"⚠️ تجاوز الحدود للمستخدم {user_id}: {error_msg}")
            
            await update.message.reply_text(
                f"❌ *تجاوز الحد المسموح!*\n\n"
                f"⚠️ {limits_check['error']}\n\n"
                f"💡 الحد المتاح: `{limits_check.get('remaining', 0)}` NSP\n"
                f"💰 الرجاء إدخال مبلغ أقل:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_withdraw')
                ]])
            )
            return
        
        # عرض تأكيد النهائي
        confirmation_text = f"""
✅ *بيانات السحب جاهزة!*

📋 *ملخص البيانات:*

👤 *اسم المستخدم:* `{withdraw_states[user_id].login}`
🆔 *رقم اللاعب:* `{withdraw_states[user_id].player_id}`
💰 *مبلغ السحب:* `{amount}` NSP

📊 *المعلومات المالية:*
• رصيد Ichancy الحالي: `{current_balance:.2f}` NSP
• رصيد Ichancy بعد السحب: `{current_balance - amount:.2f}` NSP
• رصيدك المحلي الحالي: `{user_balance:.2f}` NSP
• رصيدك المحلي بعد الإضافة: `{user_balance + amount:.2f}` NSP

⚠️ *تحذيرات هامة:*
1. سيتم خصم `{amount}` NSP من رصيد حساب Ichancy
2. سيتم إضافة `{amount}` NSP إلى رصيدك المحلي
3. العملية لا يمكن التراجع عنها
4. تأكد من صحة البيانات قبل التأكيد
5. قد تستغرق العملية 1-2 دقيقة

💡 *ملاحظات:*
• الحد الأدنى للسحب: `{config.APP_CONFIG['min_amount']}` NSP
• العمولات: لا توجد عمولات
• وقت المعالجة: 1-2 دقيقة
• للدعم: @TSA_Support

{f"🚫 *تحذير إضافي:* {limits_check.get('warning', '')}" if limits_check.get('warning') else ""}

❓ *هل تريد متابعة عملية السحب؟*
        """
        
        await update.message.reply_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ نعم، متابعة السحب", callback_data='confirm_withdraw'),
                    InlineKeyboardButton("❌ لا، إلغاء العملية", callback_data='cancel_withdraw')
                ]
            ])
        )
        
        # تسجيل تقدم العملية
        db.add_transaction({
            'user_id': user_id,
            'player_id': withdraw_states[user_id].player_id,
            'type': 'withdraw_amount_accepted',
            'amount': amount,
            'status': 'pending',
            'details': f'مبلغ السحب المقبول: {amount} NSP - الرصيد الحالي: {current_balance}'
        })
        
    except Exception as e:
        error_msg = f"❌ فشل معالجة مبلغ السحب للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='withdraw_amount_processing_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.withdraw_handler.handle_withdraw_amount'
        )
        
        await update.message.reply_text(
            f"❌ *حدث خطأ في معالجة المبلغ!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 يرجى الاتصال بالدعم: @TSA_Support\n"
            f"🔧 كود الخطأ: `{user_id[:8]}_WITHDRAW_AMOUNT_FAIL`",
            parse_mode='Markdown'
        )

async def confirm_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد وإتمام عملية السحب"""
    
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    chat_id = query.message.chat.id
    
    logger.info(f"✅ تأكيد سحب من المستخدم {user_id}")
    
    try:
        # التحقق من وجود جميع البيانات
        if user_id not in withdraw_states or not all([
            withdraw_states[user_id].amount,
            withdraw_states[user_id].player_id,
            withdraw_states[user_id].login,
            withdraw_states[user_id].current_balance is not None
        ]):
            logger.error(f"❌ بيانات غير مكتملة للمستخدم {user_id}")
            
            await query.edit_message_text(
                "❌ *بيانات غير مكتملة!*\n\n"
                "يرجى البدء من جديد باستخدام /start",
                parse_mode='Markdown'
            )
            return
        
        amount = withdraw_states[user_id].amount
        player_id = withdraw_states[user_id].player_id
        login = withdraw_states[user_id].login
        current_balance = withdraw_states[user_id].current_balance
        
        # تحديث الرسالة للإشارة إلى بدء العملية
        await query.edit_message_text(
            f"⏳ *جارٍ معالجة السحب...*\n\n"
            f"👤 المستخدم: `{login}`\n"
            f"💰 المبلغ: `{amount}` NSP\n"
            f"🆔 رقم اللاعب: `{player_id}`\n"
            f"📊 الرصيد الحالي: `{current_balance}` NSP\n\n"
            f"⏱️ قد تستغرق العملية 1-2 دقيقة\n"
            f"⚡ يرجى الانتظار...",
            parse_mode='Markdown'
        )
        
        # تسجيل بدء معالجة السحب
        db.add_transaction({
            'user_id': user_id,
            'player_id': player_id,
            'type': 'withdraw_processing',
            'amount': amount,
            'status': 'processing',
            'details': f'بدء معالجة سحب من حساب {login} - الرصيد الحالي: {current_balance}'
        })
        
        # 1. التحقق من الرصيد الحالي مرة أخرى (للتأكد)
        balance_check = api.get_balance(player_id)
        
        if not balance_check.get('success'):
            error_msg = balance_check.get('error', 'فشل التحقق من الرصيد')
            logger.error(f"❌ فشل التحقق من رصيد Ichancy للمستخدم {user_id}: {error_msg}")
            
            await query.edit_message_text(
                f"❌ *فشل التحقق من الرصيد!*\n\n"
                f"⚠️ {error_msg}\n\n"
                f"📞 للدعم: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_BALANCE_CHECK_FAIL`",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'player_id': player_id,
                'type': 'withdraw_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': 'فشل التحقق من الرصيد قبل السحب'
            })
            
            # تنظيف حالة المستخدم
            del withdraw_states[user_id]
            return
        
        updated_balance = balance_check.get('balance', current_balance)
        
        if updated_balance < amount:
            error_msg = f"❌ الرصيد غير كافي بعد التحقق. الرصيد الحالي: {updated_balance} NSP"
            logger.error(f"❌ رصيد غير كافي للمستخدم {user_id}: {error_msg}")
            
            await query.edit_message_text(
                f"❌ *الرصيد غير كافي!*\n\n"
                f"⚠️ رصيدك الحالي: `{updated_balance}` NSP\n"
                f"💰 المبلغ المطلوب: `{amount}` NSP\n\n"
                f"💡 قد يكون الرصيد قد تغير أثناء العملية",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'player_id': player_id,
                'type': 'withdraw_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': f'رصيد غير كافي بعد التحقق: {updated_balance} NSP'
            })
            
            # تنظيف حالة المستخدم
            del withdraw_states[user_id]
            return
        
        logger.info(f"✅ الرصيد الحالي مؤكد: {updated_balance} NSP للمستخدم {user_id}")
        
        # 2. سحب المبلغ من حساب Ichancy
        withdraw_result = api.withdraw(player_id, amount)
        
        if not withdraw_result.get('success'):
            error_msg = withdraw_result.get('error', 'فشل غير معروف في السحب')
            logger.error(f"❌ فشل السحب من Ichancy للمستخدم {user_id}: {error_msg}")
            
            await query.edit_message_text(
                f"❌ *فشل سحب المبلغ من Ichancy!*\n\n"
                f"⚠️ {error_msg}\n\n"
                f"📞 للدعم: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_ICHANCY_WITHDRAW_FAIL`",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'player_id': player_id,
                'type': 'withdraw_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': f'فشل السحب من Ichancy: {error_msg}'
            })
            
            # تنظيف حالة المستخدم
            del withdraw_states[user_id]
            return
        
        logger.info(f"✅ تم سحب {amount} NSP من حساب {player_id} على Ichancy")
        
        # 3. إضافة المبلغ إلى رصيد المستخدم المحلي
        addition_success = db.update_user_balance(user_id, amount, "add")
        
        if not addition_success:
            error_msg = f"❌ فشل إضافة المبلغ إلى الرصيد المحلي للمستخدم {user_id}"
            logger.error(error_msg)
            
            # محاولة استرداد المبلغ المسحوب
            try:
                recovery_result = api.deposit(player_id, amount)
                if recovery_result.get('success'):
                    recovery_msg = "تم استرداد المبلغ إلى حساب Ichancy."
                else:
                    recovery_msg = "يرجى الاتصال بالدعم لاسترداد المبلغ."
            except:
                recovery_msg = "يرجى الاتصال بالدعم لاسترداد المبلغ."
            
            await query.edit_message_text(
                f"❌ *فشل إضافة المبلغ إلى رصيدك!*\n\n"
                f"⚠️ {error_msg}\n\n"
                f"🔁 {recovery_msg}\n"
                f"📞 للدعم الفوري: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_LOCAL_BALANCE_FAIL`",
                parse_mode='Markdown'
            )
            
            db.add_transaction({
                'user_id': user_id,
                'player_id': player_id,
                'type': 'withdraw_failed',
                'amount': amount,
                'status': 'failed',
                'error_message': error_msg,
                'details': f'فشل إضافة المبلغ إلى الرصيد المحلي - {recovery_msg}'
            })
            
            # تنظيف حالة المستخدم
            del withdraw_states[user_id]
            return
        
        logger.info(f"✅ تم إضافة {amount} NSP إلى رصيد المستخدم المحلي {user_id}")
        
        # 4. جلب الرصيد الجديد على Ichancy
        final_balance_result = api.get_balance(player_id)
        
        if final_balance_result.get('success'):
            new_balance = final_balance_result.get('balance', updated_balance - amount)
            
            # تحديث رصيد الحساب في قاعدة البيانات
            db.update_account_balance(player_id, new_balance)
            
            balance_info = f"""
📊 *معلومات الرصيد على Ichancy:*
• الرصيد السابق: `{updated_balance:.2f}` NSP
• المبلغ المسحوب: `{amount}` NSP
• الرصيد الحالي: `{new_balance:.2f}` NSP
            """
        else:
            balance_info = "⚠️ *ملاحظة:* تعذر جلب الرصيد الحالي على Ichancy، يرجى التحقق يدوياً"
            new_balance = None
        
        # 5. جلب الرصيد المحلي الجديد
        final_local_balance = db.get_user_balance(user_id)
        
        # 6. إرسال رسالة النجاح
        success_message = f"""
🎉 *تم السحب بنجاح!*

✅ *تفاصيل العملية:*

👤 *اسم المستخدم:* `{login}`
🆔 *رقم اللاعب:* `{player_id}`
💰 *المبلغ المسحوب:* `{amount}` NSP
⏰ *وقت المعالجة:* فوري

{balance_info}

💰 *معلومات الرصيد المحلي:*
• الرصيد المحلي السابق: `{final_local_balance - amount:.2f}` NSP
• المبلغ المضاف: `{amount}` NSP
• الرصيد المحلي الحالي: `{final_local_balance:.2f}` NSP

📋 *ملخص المعاملة:*
• حالة المعاملة: ✅ ناجحة
• وقت التنفيذ: فوري
• الرقم المرجعي: `{user_id[:8]}_{player_id[:4]}`
• وقت التسجيل: الآن

🛡️ *تعليمات الأمان:*
1. احتفظ بهذه المعلومات لأغراض المراجعة
2. يمكنك استخدام الرصيد المحلي للعمليات الأخرى
3. للاستفسارات: @TSA_Support

💡 *ماذا بعد؟*
• يمكنك تعبئة رصيد Ichancy مرة أخرى
• يمكنك سحب رصيد إضافي عند الحاجة
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
        transaction_details = f'سحب ناجح من حساب {login} (ID: {player_id})'
        if new_balance is not None:
            transaction_details += f' - الرصيد الجديد على Ichancy: {new_balance} NSP'
        
        db.add_transaction({
            'user_id': user_id,
            'player_id': player_id,
            'type': 'withdraw',
            'amount': amount,
            'status': 'success',
            'details': transaction_details
        })
        
        logger.info(f"✅ تم إتمام سحب كامل للمستخدم {user_id}: {amount} NSP من الحساب {login}")
        
        # 8. تنظيف حالة المستخدم
        del withdraw_states[user_id]
        
    except Exception as e:
        error_msg = f"❌ فشل إتمام السحب للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='withdraw_final_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.withdraw_handler.confirm_withdraw'
        )
        
        try:
            # محاولة استرداد الحالة
            recovery_msg = ""
            if user_id in withdraw_states:
                try:
                    # التحقق مما إذا تم السحب بالفعل
                    current_balance = api.get_balance(withdraw_states[user_id].player_id)
                    if current_balance.get('success'):
                        balance = current_balance.get('balance', 0)
                        original_balance = withdraw_states[user_id].current_balance
                        
                        if balance < original_balance - 1:  # هامش خطأ
                            recovery_msg = "⚠️ قد يكون المبلغ قد سُحب بالفعل، يرجى الاتصال بالدعم."
                except:
                    pass
            
            await query.edit_message_text(
                f"❌ *حدث خطأ غير متوقع!*\n\n"
                f"⚠️ {str(e)}\n\n"
                f"{recovery_msg}\n"
                f"📞 للدعم الفوري: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_WITHDRAW_FINAL_FAIL`",
                parse_mode='Markdown'
            )
            
        except:
            pass
        
        # تنظيف حالة المستخدم في جميع الأحوال
        if user_id in withdraw_states:
            del withdraw_states[user_id]

async def cancel_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء عملية السحب"""
    
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    logger.info(f"❌ إلغاء سحب من المستخدم {user_id}")
    
    # تنظيف حالة المستخدم
    if user_id in withdraw_states:
        del withdraw_states[user_id]
    
    await query.edit_message_text(
        "❌ *تم إلغاء عملية السحب*\n\n"
        "يمكنك البدء من جديد باستخدام /start أو إعادة المحاولة",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 إعادة المحاولة", callback_data='withdraw'),
            InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')
        ]])
    )
    
    # تسجيل الإلغاء
    db.add_transaction({
        'user_id': user_id,
        'type': 'withdraw_cancelled',
        'amount': 0,
        'status': 'cancelled',
        'details': 'ألغى المستخدم عملية السحب'
    })

async def quick_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: float):
    """سحب سريع بمبلغ محدد مسبقاً"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"⚡ سحب سريع للمستخدم {user_id}: {amount} NSP")
    
    try:
        # التحقق من وجود حساب Ichancy
        ichancy_account = db.get_ichancy_account(user_id)
        
        if not ichancy_account:
            await update.message.reply_text(
                "❌ ليس لديك حساب على Ichancy!",
                parse_mode='Markdown'
            )
            return
        
        # التحقق من رصيد Ichancy
        balance_result = api.get_balance(ichancy_account['player_id'])
        
        if not balance_result.get('success'):
            await update.message.reply_text(
                f"❌ تعذر جلب الرصيد: {balance_result.get('error', 'خطأ غير معروف')}",
                parse_mode='Markdown'
            )
            return
        
        current_balance = balance_result.get('balance', 0)
        
        if current_balance < amount:
            await update.message.reply_text(
                f"❌ رصيد Ichancy غير كافي! الرصيد الحالي: {current_balance:.2f} NSP",
                parse_mode='Markdown'
            )
            return
        
        # سحب المبلغ من Ichancy
        withdraw_result = api.withdraw(ichancy_account['player_id'], amount)
        
        if not withdraw_result.get('success'):
            await update.message.reply_text(
                f"❌ فشل السحب: {withdraw_result.get('error', 'خطأ غير معروف')}",
                parse_mode='Markdown'
            )
            return
        
        # إضافة المبلغ إلى الرصيد المحلي
        addition_success = db.update_user_balance(user_id, amount, "add")
        
        if not addition_success:
            # محاولة استرداد
            try:
                api.deposit(ichancy_account['player_id'], amount)
            except:
                pass
            
            await update.message.reply_text(
                "❌ فشل إضافة المبلغ إلى الرصيد المحلي! يرجى الاتصال بالدعم.",
                parse_mode='Markdown'
            )
            return
        
        # تسجيل النجاح
        db.add_transaction({
            'user_id': user_id,
            'player_id': ichancy_account['player_id'],
            'type': 'quick_withdraw',
            'amount': amount,
            'status': 'success',
            'details': f'سحب سريع بمبلغ {amount} NSP'
        })
        
        await update.message.reply_text(
            f"✅ تم سحب {amount} NSP بنجاح!",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ فشل السحب السريع للمستخدم {user_id}: {str(e)}")
        
        await update.message.reply_text(
            f"❌ حدث خطأ: {str(e)}",
            parse_mode='Markdown'
        )

# ========== دوال التحقق ==========

def _validate_withdraw_amount(amount_str: str, user_id: str, current_balance: float) -> Dict:
    """التحقق من صحة مبلغ السحب"""
    
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
        
        # التحقق من رصيد Ichancy
        if amount > current_balance:
            return {
                'valid': False,
                'error': f'رصيد حساب Ichancy غير كافي ({current_balance:.2f} NSP)',
                'suggestion': f'اختر مبلغاً أقل من أو يساوي {current_balance:.2f} NSP',
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

async def check_withdraw_limits(user_id: str, amount: float) -> Dict:
    """التحقق من حدود السحب"""
    
    try:
        # الحصول على إحصائيات المستخدم
        user_stats = db.get_user_stats(user_id)
        
        # التحقق من الحد اليومي للسحب
        daily_withdraw_limit = 5000  # مثال: 5,000 NSP يومياً
        daily_withdrawals = user_stats.get('total_withdrawals', 0)
        
        if daily_withdrawals + amount > daily_withdraw_limit:
            return {
                'allowed': False,
                'error': f'تجاوزت الحد اليومي للسحب ({daily_withdraw_limit} NSP)',
                'remaining': daily_withdraw_limit - daily_withdrawals,
                'warning': f'لقد سحبت {daily_withdrawals} NSP اليوم، المتبقي: {daily_withdraw_limit - daily_withdrawals} NSP'
            }
        
        # التحقق من الحد لكل معاملة سحب
        per_transaction_limit = 2000  # مثال: 2,000 NSP لكل معاملة سحب
        
        if amount > per_transaction_limit:
            return {
                'allowed': False,
                'error': f'المبلغ يتجاوز الحد المسموح لكل معاملة سحب ({per_transaction_limit} NSP)',
                'remaining': per_transaction_limit,
                'warning': f'الحد الأقصى لكل سحب: {per_transaction_limit} NSP'
            }
        
        # التحقق من الحد الأسبوعي (اختياري)
        weekly_withdraw_limit = 20000  # مثال: 20,000 NSP أسبوعياً
        # يمكن تطبيق هذا بالتحقق من قاعدة البيانات
        
        return {
            'allowed': True,
            'error': None,
            'remaining': daily_withdraw_limit - daily_withdrawals,
            'warning': None
        }
        
    except Exception as e:
        logger.error(f"❌ فشل التحقق من حدود السحب للمستخدم {user_id}: {str(e)}")
        return {
            'allowed': True,  # نسمح في حالة الخطأ
            'error': f'خطأ في التحقق: {str(e)}',
            'remaining': None,
            'warning': None
        }

async def get_withdraw_history(user_id: str, limit: int = 10) -> list:
    """الحصول على سجل عمليات السحب"""
    
    try:
        transactions = db.get_user_transactions(user_id, limit)
        
        withdraw_history = []
        for transaction in transactions:
            if transaction['type'] == 'withdraw':
                withdraw_history.append({
                    'amount': transaction['amount'],
                    'status': transaction['status'],
                    'date': transaction['created_at'],
                    'player_id': transaction.get('player_id', 'N/A'),
                    'error': transaction.get('error_message')
                })
        
        return withdraw_history
        
    except Exception as e:
        logger.error(f"❌ فشل جلب سجل السحب للمستخدم {user_id}: {str(e)}")
        return []

async def show_withdraw_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل عمليات السحب"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"📜 طلب سجل السحب من المستخدم {user_id}")
    
    try:
        history = await get_withdraw_history(user_id, limit=20)
        
        if not history:
            await update.message.reply_text(
                "📭 *لا توجد عمليات سحب سابقة*",
                parse_mode='Markdown'
            )
            return
        
        history_text = "📋 *سجل عمليات السحب*\n\n"
        
        for i, withdraw in enumerate(history, 1):
            status_icon = "✅" if withdraw['status'] == 'success' else "❌"
            date = withdraw['date'].split()[0] if withdraw['date'] else "غير معروف"
            
            history_text += f"{i}. {status_icon} *{withdraw['amount']}* NSP\n"
            history_text += f"   📅 {date} | {withdraw['status']}\n"
            
            if withdraw.get('error'):
                history_text += f"   ⚠️ {withdraw['error'][:50]}...\n"
            
            history_text += "\n"
        
        await update.message.reply_text(
            history_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 العودة", callback_data='my_balance')
            ]])
        )
        
    except Exception as e:
        error_msg = f"❌ فشل عرض سجل السحب للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        await update.message.reply_text(
            f"❌ حدث خطأ في جلب السجل: {str(e)}",
            parse_mode='Markdown'
        )

async def withdraw_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """سحب الرصيد الكامل"""
    
    user_id = str(update.effective_user.id)
    
    logger.info(f"💰 طلب سحب الكامل من المستخدم {user_id}")
    
    try:
        # التحقق من وجود حساب Ichancy
        ichancy_account = db.get_ichancy_account(user_id)
        
        if not ichancy_account:
            await update.message.reply_text(
                "❌ ليس لديك حساب على Ichancy!",
                parse_mode='Markdown'
            )
            return
        
        # جلب الرصيد الحالي
        balance_result = api.get_balance(ichancy_account['player_id'])
        
        if not balance_result.get('success'):
            await update.message.reply_text(
                f"❌ تعذر جلب الرصيد: {balance_result.get('error', 'خطأ غير معروف')}",
                parse_mode='Markdown'
            )
            return
        
        current_balance = balance_result.get('balance', 0)
        
        if current_balance < config.APP_CONFIG['min_amount']:
            await update.message.reply_text(
                f"❌ الرصيد أقل من الحد الأدنى للسحب ({config.APP_CONFIG['min_amount']} NSP)",
                parse_mode='Markdown'
            )
            return
        
        # عرض تأكيد السحب الكامل
        confirmation_text = f"""
💰 *سحب الرصيد الكامل*

📊 *الرصيد المتاح:* `{current_balance:.2f}` NSP

⚠️ *هل تريد سحب الرصيد الكامل؟*
        """
        
        await update.message.reply_text(
            confirmation_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"✅ نعم، سحب {current_balance:.2f} NSP", 
                                       callback_data=f'withdraw_full_{current_balance}'),
                    InlineKeyboardButton("❌ لا، إلغاء", callback_data='cancel_withdraw')
                ]
            ])
        )
        
    except Exception as e:
        logger.error(f"❌ فشل طلب السحب الكامل للمستخدم {user_id}: {str(e)}")
        
        await update.message.reply_text(
            f"❌ حدث خطأ: {str(e)}",
            parse_mode='Markdown'
        )

if __name__ == "__main__":
    print("✅ تم تحميل معالج سحب الرصيد بنجاح")
    print("🔍 اختبار دوال التحقق:")
    
    # اختبار التحقق من المبالغ
    test_amounts = [
        ("50", "12345", 100),
        ("-10", "12345", 100),
        ("0", "12345", 100),
        ("150", "12345", 100),  # أكثر من الرصيد
        ("abc", "12345", 100)
    ]
    
    for amount_str, user_id, balance in test_amounts:
        result = _validate_withdraw_amount(amount_str, user_id, balance)
        print(f"💰 {amount_str} (User: {user_id}, Balance: {balance}): {'✅' if result['valid'] else '❌'} {result.get('error', '')}")
    
    print("\n✅ جميع الاختبارات تمت بنجاح!")
