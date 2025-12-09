import logging
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from api.ichancy_api import api
from config import config
from handlers.start_handler import (
    help_handler, 
    balance_handler, 
    stats_handler, 
    site_url_handler
)
from handlers.account_handler import (
    create_account_handler,
    confirm_account_creation,
    cancel_account_creation
)
from handlers.deposit_handler import (
    deposit_handler,
    confirm_deposit,
    cancel_deposit,
    show_deposit_history
)
from handlers.withdraw_handler import (
    withdraw_handler,
    confirm_withdraw,
    cancel_withdraw,
    show_withdraw_history,
    withdraw_all
)

logger = logging.getLogger(__name__)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع أحداث الكولباك (الأزرار)"""
    
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = str(query.from_user.id)
    chat_id = query.message.chat.id
    
    logger.info(f"🔄 كولباك من المستخدم {user_id}: {callback_data}")
    
    try:
        # ========== القائمة الرئيسية والأوامر العامة ==========
        if callback_data == 'main_menu':
            from handlers.start_handler import start_handler
            await start_handler(update, context)
            return
            
        elif callback_data == 'help':
            await help_handler(update, context)
            return
            
        elif callback_data == 'my_balance':
            await balance_handler(update, context)
            return
            
        elif callback_data == 'stats':
            await stats_handler(update, context)
            return
            
        elif callback_data == 'site_url':
            await site_url_handler(update, context)
            return
            
        # ========== إدارة الحسابات ==========
        elif callback_data == 'create_account':
            await create_account_handler(update, context)
            return
            
        elif callback_data == 'confirm_creation':
            await confirm_account_creation(update, context)
            return
            
        elif callback_data == 'cancel_creation':
            await cancel_account_creation(update, context)
            return
            
        elif callback_data == 'my_account':
            await show_account_details(update, context)
            return
            
        # ========== الإيداع ==========
        elif callback_data == 'deposit':
            await deposit_handler(update, context)
            return
            
        elif callback_data == 'confirm_deposit':
            await confirm_deposit(update, context)
            return
            
        elif callback_data == 'cancel_deposit':
            await cancel_deposit(update, context)
            return
            
        elif callback_data == 'deposit_history':
            await show_deposit_history(update, context)
            return
            
        # ========== السحب ==========
        elif callback_data == 'withdraw':
            await withdraw_handler(update, context)
            return
            
        elif callback_data == 'confirm_withdraw':
            await confirm_withdraw(update, context)
            return
            
        elif callback_data == 'cancel_withdraw':
            await cancel_withdraw(update, context)
            return
            
        elif callback_data == 'withdraw_history':
            await show_withdraw_history(update, context)
            return
            
        elif callback_data.startswith('withdraw_full_'):
            try:
                amount = float(callback_data.split('_')[2])
                from handlers.withdraw_handler import quick_withdraw
                await quick_withdraw(update, context, amount)
            except:
                await query.edit_message_text("❌ حدث خطأ في معالجة السحب الكامل")
            return
            
        # ========== المعاملات ==========
        elif callback_data == 'transactions':
            await show_all_transactions(update, context)
            return
            
        elif callback_data == 'all_transactions':
            await show_all_transactions(update, context, limit=50)
            return
            
        elif callback_data == 'refresh_stats':
            await refresh_user_stats(update, context)
            return
            
        # ========== إدخال الأسماء المقترحة ==========
        elif callback_data == 'use_suggested_name':
            await use_suggested_username(update, context)
            return
            
        elif callback_data == 'enter_new_name':
            await request_new_username(update, context)
            return
            
        # ========== حالة النظام ==========
        elif callback_data == 'api_status':
            await show_api_status(update, context)
            return
            
        elif callback_data == 'system_status':
            await show_system_status(update, context)
            return
            
        # ========== أوامر الإيداع السريع ==========
        elif callback_data.startswith('quick_deposit_'):
            try:
                amount = float(callback_data.split('_')[2])
                from handlers.deposit_handler import quick_deposit
                await quick_deposit(update, context, amount)
            except:
                await query.edit_message_text("❌ حدث خطأ في معالجة الإيداع السريع")
            return
            
        # ========== الإيداع بمبالغ محددة ==========
        elif callback_data == 'deposit_50':
            await process_quick_deposit(update, context, 50)
            return
            
        elif callback_data == 'deposit_100':
            await process_quick_deposit(update, context, 100)
            return
            
        elif callback_data == 'deposit_500':
            await process_quick_deposit(update, context, 500)
            return
            
        elif callback_data == 'deposit_1000':
            await process_quick_deposit(update, context, 1000)
            return
            
        # ========== أوامر غير معروفة ==========
        else:
            logger.warning(f"⚠️ كولباك غير معروف من المستخدم {user_id}: {callback_data}")
            await query.edit_message_text(
                "❌ *أمر غير معروف*\n\n"
                "يرجى استخدام الأزرار المتاحة فقط.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        error_msg = f"❌ فشل معالجة الكولباك {callback_data} للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        db.log_error(
            user_id=user_id,
            error_type='callback_handler_failed',
            error_message=error_msg,
            stack_trace=traceback.format_exc(),
            api_endpoint='handlers.callback_handler.handle_callback'
        )
        
        try:
            await query.edit_message_text(
                f"❌ *حدث خطأ في معالجة الأمر!*\n\n"
                f"⚠️ {str(e)[:100]}\n\n"
                f"📞 للدعم: @TSA_Support\n"
                f"🔧 كود الخطأ: `{user_id[:8]}_CALLBACK_FAIL`",
                parse_mode='Markdown'
            )
        except:
            pass

# ========== الدوال المساعدة للكولباك ==========

async def show_account_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تفاصيل حساب المستخدم"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # الحصول على معلومات المستخدم
        ichancy_account = db.get_ichancy_account(user_id)
        
        if not ichancy_account:
            await query.edit_message_text(
                "❌ *ليس لديك حساب على Ichancy!*\n\n"
                "يمكنك إنشاء حساب جديد باستخدام الزر أدناه.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🆕 إنشاء حساب جديد", callback_data='create_account')
                ]])
            )
            return
        
        # جلب الرصيد الحالي من Ichancy
        balance_result = api.get_balance(ichancy_account['player_id'])
        current_balance = balance_result.get('balance', ichancy_account['current_balance']) \
            if balance_result.get('success') else ichancy_account['current_balance']
        
        # تحديث الرصيد في قاعدة البيانات
        db.update_account_balance(ichancy_account['player_id'], current_balance)
        
        # عرض تفاصيل الحساب
        account_info = f"""
👤 *معلومات حساب Ichancy*

📋 *البيانات الأساسية:*
• 👤 *اسم المستخدم:* `{ichancy_account['login']}`
• 📧 *الإيميل:* `{ichancy_account['email']}`
• 🆔 *رقم اللاعب:* `{ichancy_account['player_id']}`
• 📊 *الحالة:* `{ichancy_account['status']}`

💰 *المعلومات المالية:*
• 💰 *الرصيد الحالي:* `{current_balance:.2f}` NSP
• 💳 *الرصيد الابتدائي:* `{ichancy_account['initial_balance']}` NSP
• 📈 *صافي الأرباح:* `{current_balance - ichancy_account['initial_balance']:.2f}` NSP

📅 *معلومات التسجيل:*
• ⏰ *تاريخ الإنشاء:* `{ichancy_account['created_at']}`
• 🔄 *آخر تحديث:* `{ichancy_account['updated_at']}`

⚠️ *ملاحظة:* احفظ هذه البيانات في مكان آمن!
        """
        
        keyboard = [
            [
                InlineKeyboardButton("💰 تعبئة الرصيد", callback_data='deposit'),
                InlineKeyboardButton("💳 سحب الرصيد", callback_data='withdraw')
            ],
            [
                InlineKeyboardButton("🔄 تحديث الرصيد", callback_data='refresh_account'),
                InlineKeyboardButton("📊 رصيدي الكلي", callback_data='my_balance')
            ],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            account_info,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        error_msg = f"❌ فشل عرض تفاصيل الحساب للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        await query.edit_message_text(
            f"❌ *حدث خطأ في جلب معلومات الحساب!*\n\n"
            f"⚠️ {str(e)}\n\n"
            f"📞 للدعم: @TSA_Support",
            parse_mode='Markdown'
        )

async def show_all_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE, limit: int = 20):
    """عرض جميع المعاملات"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        transactions = db.get_user_transactions(user_id, limit)
        
        if not transactions:
            await query.edit_message_text(
                "📭 *لا توجد معاملات سابقة*",
                parse_mode='Markdown'
            )
            return
        
        transactions_text = "📋 *سجل المعاملات*\n\n"
        
        for i, transaction in enumerate(transactions, 1):
            # تحديد نوع المعاملة
            if transaction['type'] == 'deposit':
                trans_type = "إيداع"
                emoji = "💰"
            elif transaction['type'] == 'withdraw':
                trans_type = "سحب"
                emoji = "💳"
            elif transaction['type'] == 'account_creation':
                trans_type = "إنشاء حساب"
                emoji = "🆕"
            else:
                trans_type = transaction['type']
                emoji = "📄"
            
            # تحديد حالة المعاملة
            if transaction['status'] == 'success':
                status_icon = "✅"
            elif transaction['status'] == 'failed':
                status_icon = "❌"
            elif transaction['status'] == 'pending':
                status_icon = "⏳"
            else:
                status_icon = "📝"
            
            # تنسيق التاريخ
            date = transaction['created_at'].split()[0] if transaction['created_at'] else "غير معروف"
            
            transactions_text += f"{i}. {emoji} *{trans_type}* {status_icon}\n"
            transactions_text += f"   💰 `{transaction['amount']}` NSP | 📅 {date}\n"
            
            if transaction.get('player_id'):
                transactions_text += f"   🆔 `{transaction['player_id'][:8]}...`\n"
            
            if transaction.get('error_message'):
                transactions_text += f"   ⚠️ {transaction['error_message'][:40]}...\n"
            
            transactions_text += "\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 تحديث القائمة", callback_data='transactions')],
            [InlineKeyboardButton("🔙 العودة", callback_data='my_balance')]
        ]
        
        await query.edit_message_text(
            transactions_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        error_msg = f"❌ فشل عرض المعاملات للمستخدم {user_id}: {str(e)}"
        logger.error(error_msg)
        
        await query.edit_message_text(
            f"❌ *حدث خطأ في جلب سجل المعاملات!*\n\n"
            f"⚠️ {str(e)}",
            parse_mode='Markdown'
        )

async def refresh_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديث إحصائيات المستخدم"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    await query.answer("🔄 جارٍ تحديث الإحصائيات...")
    
    try:
        # تحديث رصيد حساب Ichancy إذا كان موجوداً
        ichancy_account = db.get_ichancy_account(user_id)
        if ichancy_account:
            balance_result = api.get_balance(ichancy_account['player_id'])
            if balance_result.get('success'):
                db.update_account_balance(ichancy_account['player_id'], balance_result['balance'])
        
        # تحديث الرسالة
        from handlers.start_handler import stats_handler
        await stats_handler(update, context)
        
    except Exception as e:
        logger.error(f"❌ فشل تحديث الإحصائيات للمستخدم {user_id}: {str(e)}")
        await query.answer("❌ فشل التحديث")

async def use_suggested_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استخدام اسم المستخدم المقترح"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    from handlers.account_handler import user_states
    
    try:
        if user_id in user_states and user_states[user_id].username:
            # المتابعة إلى خطوة كلمة المرور
            from handlers.account_handler import handle_password_input
            
            # إنشاء رسالة وهمية للمتابعة
            class MockUpdate:
                def __init__(self, query):
                    self.message = MockMessage(query)
                    self.effective_user = query.from_user
                    
            class MockMessage:
                def __init__(self, query):
                    self.text = "password_placeholder"
                    self.chat = query.message.chat
                    self.reply_text = query.edit_message_text
            
            mock_update = MockUpdate(query)
            
            # التبديل إلى وضع انتظار كلمة المرور
            user_states[user_id].step = 'password'
            
            await query.edit_message_text(
                "✅ *تم قبول الاسم المقترح!*\n\n"
                "🔐 *الخطوة التالية: إدخال كلمة المرور*\n\n"
                "الرجاء إدخال كلمة المرور الآن...",
                parse_mode='Markdown'
            )
            
        else:
            await query.edit_message_text(
                "❌ *لم يتم العثور على اسم مستخدم مقترح!*\n\n"
                "يرجى البدء من جديد.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"❌ فشل استخدام الاسم المقترح للمستخدم {user_id}: {str(e)}")
        
        await query.edit_message_text(
            f"❌ *حدث خطأ!*\n\n"
            f"⚠️ {str(e)}",
            parse_mode='Markdown'
        )

async def request_new_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب اسم مستخدم جديد"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    from handlers.account_handler import user_states
    
    try:
        if user_id in user_states:
            user_states[user_id].step = 'username'
            
            await query.edit_message_text(
                "✍️ *الرجاء إدخال اسم مستخدم جديد:*\n\n"
                "📝 *المتطلبات:*\n"
                "• أحرف لاتينية فقط (A-Z, a-z)\n"
                "• يمكن استخدام الأرقام والنقاط والشرطات\n"
                "• الطول: 3-20 حرفاً\n\n"
                "💡 *أمثلة:* john_doe, user.tsa, player2024",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 إلغاء العملية", callback_data='cancel_creation')
                ]])
            )
            
        else:
            await query.edit_message_text(
                "❌ *جلسة منتهية!*\n\n"
                "يرجى البدء من جديد.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"❌ فشل طلب اسم مستخدم جديد للمستخدم {user_id}: {str(e)}")
        
        await query.edit_message_text(
            f"❌ *حدث خطأ!*\n\n"
            f"⚠️ {str(e)}",
            parse_mode='Markdown'
        )

async def show_api_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة واجهة برمجة التطبيقات"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # اختبار الاتصال بـ Ichancy API
        login_result = api.login()
        
        api_status = "✅ نشط" if login_result.get('success') else "❌ غير نشط"
        api_message = login_result.get('error', 'غير معروف') if not login_result.get('success') else 'يعمل بشكل طبيعي'
        
        # التحقق من إعدادات التطبيق
        config_status = "✅ مكتمل" if all([
            config.BOT_TOKEN,
            config.AGENT_USERNAME,
            config.AGENT_PASSWORD,
            config.PARENT_ID
        ]) else "❌ غير مكتمل"
        
        # التحقق من قاعدة البيانات
        try:
            test_balance = db.get_user_balance(user_id)
            db_status = "✅ متصل"
        except:
            db_status = "❌ غير متصل"
        
        status_text = f"""
🔧 *حالة النظام*

📊 *واجهة Ichancy API:*
• الحالة: {api_status}
• الرسالة: {api_message}

⚙️ *إعدادات التطبيق:*
• التوكن: {'✅' if config.BOT_TOKEN else '❌'}
• اسم المستخدم: {'✅' if config.AGENT_USERNAME else '❌'}
• كلمة المرور: {'✅' if config.AGENT_PASSWORD else '❌'}
• Parent ID: {'✅' if config.PARENT_ID else '❌'}
• الحالة العامة: {config_status}

🗄️ *قاعدة البيانات:*
• الحالة: {db_status}
• النوع: {db.db_type}

🌐 *البيئة:*
• البيئة: {config.RAILWAY_ENVIRONMENT}
• الوضع: {'إنتاج ⚡' if config.IS_PRODUCTION else 'تطوير 🛠️'}

💡 *ملاحظة:* هذه المعلومات خاصة بالنظام.
        """
        
        await query.edit_message_text(
            status_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 تحديث الحالة", callback_data='api_status'),
                InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')
            ]])
        )
        
    except Exception as e:
        logger.error(f"❌ فشل عرض حالة API للمستخدم {user_id}: {str(e)}")
        
        await query.edit_message_text(
            f"❌ *حدث خطأ في جلب حالة النظام!*\n\n"
            f"⚠️ {str(e)}",
            parse_mode='Markdown'
        )

async def show_system_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة النظام العام"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # جلب إحصائيات النظام
        user_stats = db.get_user_stats(user_id)
        
        # حساب بعض الإحصائيات
        total_operations = user_stats.get('account_count', 0) + \
                          user_stats.get('failed_transactions', 0)
        
        success_rate = 0
        if total_operations > 0:
            success_rate = (user_stats.get('account_count', 0) / total_operations) * 100
        
        status_text = f"""
📊 *إحصائيات النظام*

👥 *إحصائيات المستخدم:*
• الحسابات النشطة: `{user_stats.get('account_count', 0)}`
• إجمالي الإيداعات: `{user_stats.get('total_deposits', 0):.2f}` NSP
• إجمالي السحوبات: `{user_stats.get('total_withdrawals', 0):.2f}` NSP
• المعاملات الفاشلة: `{user_stats.get('failed_transactions', 0)}`
• نسبة النجاح: `{success_rate:.1f}%`

💼 *رصيدك المالي:*
• الرصيد المحلي: `{db.get_user_balance(user_id):.2f}` NSP
• صافي الرصيد: `{user_stats.get('net_balance', 0):.2f}` NSP

⚙️ *إعدادات التطبيق:*
• الحد الأدنى للمعاملة: `{config.APP_CONFIG['min_amount']}` NSP
• الحد الأقصى لكلمة المرور: `{config.APP_CONFIG['max_password_length']}` حرف
• مدة الجلسة: `{config.APP_CONFIG['session_timeout']//3600}` ساعة

🔄 *آخر تحديث:* الآن
        """
        
        keyboard = [
            [InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data='refresh_stats')],
            [InlineKeyboardButton("📜 سجل المعاملات", callback_data='all_transactions')],
            [InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            status_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"❌ فشل عرض حالة النظام للمستخدم {user_id}: {str(e)}")
        
        await query.edit_message_text(
            f"❌ *حدث خطأ في جلب إحصائيات النظام!*\n\n"
            f"⚠️ {str(e)}",
            parse_mode='Markdown'
        )

async def refresh_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديث معلومات الحساب"""
    
    query = update.callback_query
    await query.answer("🔄 جارٍ تحديث معلومات الحساب...")
    
    # إعادة عرض تفاصيل الحساب
    await show_account_details(update, context)

async def process_quick_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: float):
    """معالجة الإيداع السريع بمبلغ محدد"""
    
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    from handlers.deposit_handler import quick_deposit
    
    try:
        await quick_deposit(update, context, amount)
    except Exception as e:
        logger.error(f"❌ فشل الإيداع السريع للمستخدم {user_id}: {str(e)}")
        
        await query.edit_message_text(
            f"❌ *فشل الإيداع السريع!*\n\n"
            f"⚠️ {str(e)}",
            parse_mode='Markdown'
        )

if __name__ == "__main__":
    print("✅ تم تحميل معالج الكولباك بنجاح")
    print("🔍 النظام جاهز لمعالجة الأزرار والأوامر!")
