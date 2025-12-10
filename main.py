"""
الملف الرئيسي لتشغيل بوت Ichancy على Railway - نسخة مستقلة
"""

import os
import sys
import logging
import asyncio
from datetime import datetime

# إضافة المسار الحالي للمسارات
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.error import TelegramError
import config
from utils.logger import setup_logger

# إعداد التسجيل
logger = setup_logger('ichancy_bot')

def main():
    """الدالة الرئيسية التشغيلية"""
    
    try:
        logger.info("=" * 60)
        logger.info("🚀 بدء تشغيل بوت Ichancy")
        logger.info(f"📅 وقت البدء: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🌐 البيئة: {config.RAILWAY_ENVIRONMENT}")
        logger.info("=" * 60)
        
        # التحقق من إعدادات التطبيق
        if not all([config.BOT_TOKEN, config.AGENT_USERNAME, config.AGENT_PASSWORD]):
            logger.error("❌ إعدادات التطبيق غير مكتملة!")
            sys.exit(1)
        
        # إنشاء تطبيق التليجرام
        logger.info("🔧 جاري إنشاء تطبيق البوت...")
        application = Application.builder().token(config.BOT_TOKEN).build()
        
        # استيراد handlers بعد إنشاء التطبيق
        from handlers import start_handler, account_handler, deposit_handler, withdraw_handler, callback_handler
        
        # إعداد المعالجات
        logger.info("🔧 جاري إعداد المعالجات...")
        
        # معالجة أمر /start
        application.add_handler(CommandHandler("start", start_handler.start_handler))
        
        # محاولة إضافة الأوامر الأخرى
        try:
            application.add_handler(CommandHandler("help", start_handler.help_handler))
            application.add_handler(CommandHandler("balance", start_handler.balance_handler))
            application.add_handler(CommandHandler("stats", start_handler.stats_handler))
        except AttributeError as e:
            logger.warning(f"⚠️ بعض المعالجات غير متوفرة: {e}")
        
        # معالجة إنشاء الحساب
        application.add_handler(CommandHandler("create_account", account_handler.create_account_handler))
        
        # معالجة تعبئة الرصيد
        application.add_handler(CommandHandler("deposit", deposit_handler.deposit_handler))
        
        # معالجة سحب الرصيد
        application.add_handler(CommandHandler("withdraw", withdraw_handler.withdraw_handler))
        
        # معالجة الأزرار (Callback Queries)
        application.add_handler(CallbackQueryHandler(callback_handler.handle_callback))
        
        # معالجة إدخال النصوص
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            handle_text_input
        ))
        
        logger.info("✅ تم إعداد المعالجات بنجاح")
        
        # بدء البوت في وضع Polling
        logger.info("🚀 بدء تشغيل البوت في وضع Polling...")
        
        # تشغيل البوت - الطريقة الصحيحة لـ PTB v20+
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
        
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت بواسطة المستخدم")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {str(e)}")
        sys.exit(1)

async def handle_text_input(update, context):
    """معالجة إدخال النصوص"""
    
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    
    try:
        logger.info(f"📝 إدخال نص من المستخدم {user_id}: {text[:50]}...")
        
        # التحقق من حالة إنشاء الحساب
        from handlers.account_handler import user_states
        if user_id in user_states:
            state = user_states[user_id]
            
            if state.step == 'username':
                from handlers.account_handler import handle_username_input
                await handle_username_input(update, context)
            elif state.step == 'password':
                from handlers.account_handler import handle_password_input
                await handle_password_input(update, context)
            elif state.step == 'amount':
                from handlers.account_handler import handle_amount_input
                await handle_amount_input(update, context)
            else:
                await update.message.reply_text(
                    "❌ حالة غير معروفة، يرجى البدء من جديد باستخدام /start",
                    parse_mode='Markdown'
                )
            return
        
        # التحقق من حالة الإيداع
        from handlers.deposit_handler import deposit_states
        if user_id in deposit_states:
            state = deposit_states[user_id]
            
            if state.step == 'amount':
                from handlers.deposit_handler import handle_deposit_amount
                await handle_deposit_amount(update, context)
            else:
                await update.message.reply_text(
                    "❌ حالة غير معروفة، يرجى البدء من جديد",
                    parse_mode='Markdown'
                )
            return
        
        # التحقق من حالة السحب
        from handlers.withdraw_handler import withdraw_states
        if user_id in withdraw_states:
            state = withdraw_states[user_id]
            
            if state.step == 'amount':
                from handlers.withdraw_handler import handle_withdraw_amount
                await handle_withdraw_amount(update, context)
            else:
                await update.message.reply_text(
                    "❌ حالة غير معروفة، يرجى البدء من جديد",
                    parse_mode='Markdown'
                )
            return
        
        # إذا لم يكن هناك حالة نشطة، عرض رسالة مساعدة
        await update.message.reply_text(
            "🤖 *مرحباً بك في بوت Ichancy*\n\n"
            "💡 *الأوامر المتاحة:*\n"
            "/start - عرض القائمة الرئيسية\n"
            "/help - عرض دليل الاستخدام\n"
            "/create_account - إنشاء حساب جديد\n"
            "/deposit - تعبئة الرصيد\n"
            "/withdraw - سحب الرصيد\n\n"
            "📞 للدعم: @TSA_Support",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ فشل معالجة الإدخال النصي للمستخدم {user_id}: {str(e)}")
        
        await update.message.reply_text(
            "❌ حدث خطأ في معالجة طلبك. يرجى المحاولة مرة أخرى.",
            parse_mode='Markdown'
        )

if __name__ == "__main__":
    # تشغيل البرنامج
    main()
