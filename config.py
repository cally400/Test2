# config.py
import os
import redis
from typing import Dict, Any, Optional

class Config:
    """إعدادات التطبيق للـ Railway"""
    
    # ========== إعدادات Railway ==========
    RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "production")
    PORT = int(os.getenv("PORT", 8000))
    IS_PRODUCTION = RAILWAY_ENVIRONMENT == "production"
    
    # ========== إعدادات Telegram Bot ==========
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    ADMIN_USER_IDS = os.getenv("ADMIN_USER_IDS", "").split(",") if os.getenv("ADMIN_USER_IDS") else []
    
    # ========== إعدادات Ichancy API ==========
    AGENT_USERNAME = os.getenv("AGENT_USERNAME", "")
    AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "")
    PARENT_ID = os.getenv("PARENT_ID", "")
    
    # ========== إعدادات قاعدة البيانات ==========
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    
    # ========== إعدادات Redis للتخزين المؤقت ==========
    REDIS_URL = os.getenv("REDIS_URL", "")
    
    # ========== إعدادات API URLs ==========
    ORIGIN = "https://agents.ichancy.com"
    API_ENDPOINTS = {
        "signin": f"{ORIGIN}/global/api/User/signIn",
        "create_player": f"{ORIGIN}/global/api/Player/registerPlayer",
        "statistics": f"{ORIGIN}/global/api/Statistics/getPlayersStatisticsPro",
        "deposit": f"{ORIGIN}/global/api/Player/depositToPlayer",
        "withdraw": f"{ORIGIN}/global/api/Player/withdrawFromPlayer",
        "balance": f"{ORIGIN}/global/api/Player/getPlayerBalanceById"
    }
    
    # ========== إعدادات التطبيق ==========
    APP_CONFIG = {
        "min_amount": 10,
        "max_password_length": 11,
        "min_password_length": 8,
        "request_delay": 2,
        "max_retries": 3,
        "session_timeout": 3600,
        "cookie_key": "ichancy:cookies",
        "cache_ttl": 300  # 5 دقائق
    }
    
    # ========== إعدادات User Agents ==========
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    
    @classmethod
    def validate(cls) -> Dict[str, bool]:
        """التحقق من صحة الإعدادات"""
        validation = {
            "bot_token": bool(cls.BOT_TOKEN),
            "agent_username": bool(cls.AGENT_USERNAME),
            "agent_password": bool(cls.AGENT_PASSWORD),
            "parent_id": bool(cls.PARENT_ID),
            "database_url": bool(cls.DATABASE_URL),
        }
        
        missing = [key for key, valid in validation.items() if not valid]
        
        if missing and cls.IS_PRODUCTION:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return validation
    
    @classmethod
    def get_redis_client(cls) -> Optional[redis.Redis]:
        """الحصول على عميل Redis"""
        if cls.REDIS_URL:
            try:
                return redis.from_url(cls.REDIS_URL, decode_responses=True)
            except Exception:
                return None
        return None
    
    @classmethod
    def get_db_config(cls) -> Dict[str, Any]:
        """الحصول على إعدادات قاعدة البيانات"""
        if cls.DATABASE_URL:
            return {"connection_string": cls.DATABASE_URL}
        return {"db_path": "ichancy_bot.db"}

config = Config()

if __name__ == "__main__":
    try:
        config.validate()
        print("✅ Configuration validated successfully")
        print(f"Environment: {config.RAILWAY_ENVIRONMENT}")
        print(f"Bot Token: {'✓' if config.BOT_TOKEN else '✗'}")
        print(f"Database: {'✓' if config.DATABASE_URL else '✗'}")
        print(f"Redis: {'✓' if config.REDIS_URL else '✗'}")
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
