# main.py
"""
الملف الرئيسي لتشغيل بوت Ichancy على Railway
"""

import os
import sys
import logging
import signal
import asyncio
from threading import Thread
from datetime import datetime

# إضافة المسار الحالي للمسارات
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telegram.ext import (
    Application, 
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)
from telegram import Update

# استيراد المكونات الخاصة بالتطبيق
from config import config
from utils.logger import setup_all_loggers
from handlers import (
    start_handler,
    account_handler,
    deposit_handler,
    withdraw_handler,
    callback_handler
)
from database import db
from api.ichancy_api import api
from api.captcha_solver import captcha_solver

# إعداد التسجيل
logger = setup_all_loggers()

class IchancyBot:
    """فئة رئيسية لإدارة بوت Ichancy"""
    
    def __init__(self):
        self.application = None
        self.is_running = False
        self.start_time = None
        
    async def init_bot(self):
        """تهيئة البوت"""
        
        try:
            logger.info("🔧 جاري تهيئة بوت Ichancy...")
            
            # التحقق من إعدادات التطبيق
            validation = config.validate()
            logger.info(f"📋 نتائج التحقق: {validation}")
            
            # التحقق من إعدادات API
            if not all([config.BOT_TOKEN, config.AGENT_USERNAME, config.AGENT_PASSWORD]):
                logger.error("❌ إعدادات التطبيق غير مكتملة!")
                return False
            
            # إنشاء تطبيق التليجرام
            self.application = ApplicationBuilder().token(config.BOT_TOKEN).build()
            
            # تسجيل وقت البدء
            self.start_time = datetime.now()
            
            logger.info("✅ تم تهيئة البوت بنجاح")
            return True
            
        except Exception as e:
            logger.error(f"❌ فشل تهيئة البوت: {str(e)}")
            return False
    
    def setup_handlers(self):
        """إعداد المعالجات والأوامر"""
        
        try:
            logger.info("🔧 جاري إعداد المعالجات...")
            
            # معالجة أمر /start
            self.application.add_handler(CommandHandler("start", start_handler.start_handler))
            self.application.add_handler(CommandHandler("help", start_handler.help_handler))
            self.application.add_handler(CommandHandler("balance", start_handler.balance_handler))
            self.application.add_handler(CommandHandler("stats", start_handler.stats_handler))
            
            # معالجة إنشاء الحساب
            self.application.add_handler(CommandHandler("create_account", account_handler.create_account_handler))
            
            # معالجة تعبئة الرصيد
            self.application.add_handler(CommandHandler("deposit", deposit_handler.deposit_handler))
            
            # معالجة سحب الرصيد
            self.application.add_handler(CommandHandler("withdraw", withdraw_handler.withdraw_handler))
            
            # معالجة إدخال النصوص
            self.application.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND, 
                self.handle_text_input
            ))
            
            # معالجة الأزرار (Callback Queries)
            self.application.add_handler(CallbackQueryHandler(callback_handler.handle_callback))
            
            logger.info("✅ تم إعداد المعالجات بنجاح")
            
        except Exception as e:
            logger.error(f"❌ فشل إعداد المعالجات: {str(e)}")
            raise
    
    async def handle_text_input(self, update: Update, context):
        """معالجة إدخال النصوص"""
        
        user_id = str(update.effective_user.id)
        text = update.message.text.strip()
        
        try:
            logger.info(f"📝 إدخال نص من المستخدم {user_id}: {text}")
            
            # التحقق من حالة إنشاء الحساب
            from handlers.account_handler import user_states
            if user_id in user_states:
                state = user_states[user_id]
                
                if state.step == 'username':
                    await account_handler.handle_username_input(update, context)
                elif state.step == 'password':
                    await account_handler.handle_password_input(update, context)
                elif state.step == 'amount':
                    await account_handler.handle_amount_input(update, context)
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
                    await deposit_handler.handle_deposit_amount(update, context)
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
                    await withdraw_handler.handle_withdraw_amount(update, context)
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
                "/balance - عرض رصيدك\n"
                "/stats - عرض إحصائياتك\n"
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
    
    async def start_polling(self):
        """بدء البوت في وضع Polling"""
        
        try:
            logger.info("🚀 بدء البوت في وضع Polling...")
            
            self.is_running = True
            
            # إعداد المعالجات
            self.setup_handlers()
            
            # بدء Polling
            await self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30,
                poll_interval=0.5
            )
            
        except Exception as e:
            logger.error(f"❌ توقف البوت عن العمل: {str(e)}")
            self.is_running = False
            raise
    
    async def start_webhook(self):
        """بدء البوت في وضع Webhook (لـ Railway)"""
        
        try:
            logger.info("🌐 بدء البوت في وضع Webhook...")
            
            self.is_running = True
            
            # إعداد المعالجات
            self.setup_handlers()
            
            # إعداد Webhook لـ Railway
            webhook_url = f"https://{os.getenv('RAILWAY_STATIC_URL', '')}/webhook"
            if not webhook_url.startswith("https://"):
                webhook_url = f"https://{webhook_url}"
            
            logger.info(f"🔗 جاري إعداد Webhook: {webhook_url}")
            
            # ضبط Webhook
            await self.application.bot.set_webhook(
                url=webhook_url,
                certificate=None,
                max_connections=40,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
            # بدء Webhook
            await self.application.run_webhook(
                listen="0.0.0.0",
                port=config.PORT,
                url_path="webhook",
                webhook_url=webhook_url,
                drop_pending_updates=True
            )
            
        except Exception as e:
            logger.error(f"❌ فشل بدء Webhook: {str(e)}")
            self.is_running = False
            raise
    
    def get_bot_info(self):
        """الحصول على معلومات البوت"""
        
        if not self.application or not self.application.bot:
            return {
                "status": "غير نشط",
                "username": "غير معروف",
                "start_time": str(self.start_time) if self.start_time else "غير معروف"
            }
        
        try:
            bot_info = self.application.bot.get_me()
            
            return {
                "status": "نشط" if self.is_running else "متوقف",
                "username": bot_info.username,
                "first_name": bot_info.first_name,
                "id": bot_info.id,
                "start_time": str(self.start_time) if self.start_time else "غير معروف",
                "uptime": str(datetime.now() - self.start_time) if self.start_time else "غير معروف"
            }
            
        except Exception as e:
            logger.error(f"❌ فشل جلب معلومات البوت: {str(e)}")
            return {"status": "خطأ", "error": str(e)}
    
    async def cleanup(self):
        """تنظيف الموارد قبل الإغلاق"""
        
        try:
            logger.info("🧹 جاري تنظيف الموارد...")
            
            self.is_running = False
            
            # إغلاق اتصالات قاعدة البيانات
            logger.info("🗄️ جاري إغلاق اتصالات قاعدة البيانات...")
            
            # إغلاق جلسات API
            logger.info("🌐 جاري إغلاق جلسات API...")
            
            logger.info("✅ تم التنظيف بنجاح")
            
        except Exception as e:
            logger.error(f"❌ حدث خطأ أثناء التنظيف: {str(e)}")

async def run_bot():
    """تشغيل البوت"""
    
    bot = IchancyBot()
    
    try:
        # تهيئة البوت
        if not await bot.init_bot():
            logger.error("❌ فشل تهيئة البوت، جاري الإغلاق...")
            return
        
        # التحقق من البيئة وتشغيل الوضع المناسب
        if config.IS_PRODUCTION:
            logger.info("⚡ جاري التشغيل في وضع الإنتاج (Webhook)")
            await bot.start_webhook()
        else:
            logger.info("🛠️ جاري التشغيل في وضع التطوير (Polling)")
            await bot.start_polling()
            
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت بواسطة المستخدم")
        
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {str(e)}")
        
    finally:
        # تنظيف الموارد
        await bot.cleanup()

def signal_handler(signum, frame):
    """معالجة إشارات النظام"""
    
    logger.info(f"📡 استلام إشارة النظام: {signum}")
    sys.exit(0)

async def health_check():
    """فحص صحة النظام"""
    
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        # فحص قاعدة البيانات
        try:
            test_balance = db.get_user_balance("system_test")
            health_status["components"]["database"] = {
                "status": "healthy",
                "message": "Connected successfully"
            }
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "message": str(e)
            }
            health_status["status"] = "degraded"
        
        # فحص Ichancy API
        try:
            login_result = api.login()
            health_status["components"]["ichancy_api"] = {
                "status": "healthy" if login_result.get('success') else "unhealthy",
                "message": login_result.get('error', 'Connected successfully')
            }
            
            if not login_result.get('success'):
                health_status["status"] = "degraded"
                
        except Exception as e:
            health_status["components"]["ichancy_api"] = {
                "status": "unhealthy",
                "message": str(e)
            }
            health_status["status"] = "degraded"
        
        # فحص البوت
        bot = IchancyBot()
        bot_info = bot.get_bot_info()
        health_status["components"]["telegram_bot"] = {
            "status": bot_info.get("status", "unknown"),
            "username": bot_info.get("username", "unknown"),
            "uptime": bot_info.get("uptime", "unknown")
        }
        
        if bot_info.get("status") != "نشط":
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"❌ فشل فحص الصحة: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def run_health_server():
    """تشغيل خادم فحص الصحة البسيط"""
    
    try:
        import http.server
        import socketserver
        import json
        
        class HealthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/health':
                    # فحص الصحة بشكل متزامن
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    health_status = loop.run_until_complete(health_check())
                    loop.close()
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(health_status, ensure_ascii=False).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                logger.debug(f"🌐 Health Server: {format % args}")
        
        port = int(os.getenv("HEALTH_CHECK_PORT", 8080))
        with socketserver.TCPServer(("0.0.0.0", port), HealthHandler) as httpd:
            logger.info(f"🏥 خادم فحص الصحة يعمل على المنفذ {port}")
            httpd.serve_forever()
            
    except Exception as e:
        logger.error(f"❌ فشل تشغيل خادم فحص الصحة: {str(e)}")

def main():
    """الدالة الرئيسية للتشغيل"""
    
    try:
        # إعداد معالجات الإشارات
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("=" * 60)
        logger.info("🚀 بدء تشغيل بوت Ichancy")
        logger.info(f"📅 وقت البدء: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🌐 البيئة: {config.RAILWAY_ENVIRONMENT}")
        logger.info(f"⚙️ الوضع: {'إنتاج ⚡' if config.IS_PRODUCTION else 'تطوير 🛠️'}")
        logger.info("=" * 60)
        
        # تشغيل خادم فحص الصحة في خيط منفصل
        if config.IS_PRODUCTION:
            health_thread = Thread(target=run_health_server, daemon=True)
            health_thread.start()
            logger.info("✅ تم تشغيل خادم فحص الصحة")
        
        # تشغيل البوت
        asyncio.run(run_bot())
        
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في الدالة الرئيسية: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
