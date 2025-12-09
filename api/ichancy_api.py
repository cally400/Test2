# api/ichancy_api.py
import json
import time
import random
import logging
import traceback
from typing import Dict, Optional, Tuple, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import config
from database import db

logger = logging.getLogger(__name__)

class IchancyAPI:
    """واجهة برمجة تطبيقات Ichancy مع إدارة أخطاء مفصلة"""
    
    def __init__(self):
        self.session = self._create_session()
        self.is_logged_in = False
        self.login_attempts = 0
        self.last_login_time = 0
        self.redis_client = config.get_redis_client()
        self._setup_headers()
        
        # محاولة تحميل الكوكيز المحفوظة
        self._load_cookies()
    
    def _create_session(self):
        """إنشاء جلسة مع إعادة المحاولة"""
        session = requests.Session()
        
        # إعداد إعادة المحاولة
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _setup_headers(self):
        """إعداد رؤوس HTTP"""
        user_agent = random.choice(config.USER_AGENTS)
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/json',
            'Origin': config.ORIGIN,
            'Referer': config.ORIGIN + '/dashboard',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'DNT': '1',
            'Sec-CH-UA': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
        })
    
    def _save_cookies(self):
        """حفظ الكوكيز في Redis أو قاعدة البيانات"""
        try:
            cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
            cookies_json = json.dumps(cookies_dict)
            
            if self.redis_client:
                # حفظ في Redis
                self.redis_client.setex(
                    config.APP_CONFIG["cookie_key"],
                    config.APP_CONFIG["session_timeout"],
                    cookies_json
                )
                logger.debug("💾 تم حفظ الكوكيز في Redis")
            else:
                # حفظ في قاعدة البيانات
                from datetime import datetime, timedelta
                expiry = datetime.now() + timedelta(seconds=config.APP_CONFIG["session_timeout"])
                db.add_transaction({
                    'user_id': 'system',
                    'player_id': 'cookies',
                    'type': 'cookie_store',
                    'amount': 0,
                    'status': 'stored',
                    'details': f'Cookies saved until {expiry}'
                })
                logger.debug("💾 تم حفظ الكوكيز في قاعدة البيانات")
                
        except Exception as e:
            logger.error(f"❌ فشل حفظ الكوكيز: {str(e)}")
    
    def _load_cookies(self):
        """تحميل الكوكيز من Redis أو قاعدة البيانات"""
        try:
            cookies_json = None
            
            if self.redis_client:
                # تحميل من Redis
                cookies_json = self.redis_client.get(config.APP_CONFIG["cookie_key"])
            else:
                # محاولة تحميل من قاعدة البيانات (محاكاة)
                cookies_json = None  # نستخدم التخزين المؤقت في الذاكرة
            
            if cookies_json:
                cookies_dict = json.loads(cookies_json)
                self.session.cookies.update(cookies_dict)
                self.is_logged_in = True
                logger.info("✅ تم تحميل الكوكيز المحفوظة")
                
        except Exception as e:
            logger.error(f"❌ فشل تحميل الكوكيز: {str(e)}")
    
    def _human_delay(self):
        """تأخير يشبه السلوك البشري"""
        delay = random.uniform(1.5, 3.5)
        time.sleep(delay)
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Tuple[Optional[requests.Response], Dict]:
        """إجراء طلب آمن مع تسجيل الأخطاء"""
        url = config.API_ENDPOINTS.get(endpoint, endpoint)
        
        try:
            self._human_delay()
            
            logger.debug(f"🌐 إرسال طلب إلى: {endpoint}")
            response = self.session.request(method, url, timeout=30, **kwargs)
            
            # تسجيل الطلب والرد
            request_data = {
                'method': method,
                'url': url,
                'headers': dict(self.session.headers),
                'data': kwargs.get('json', {})
            }
            
            # محاولة تحليل الرد
            try:
                response_data = response.json()
            except:
                response_data = {'raw_response': response.text[:500]}
            
            # التحقق من حالة الرد
            if response.status_code == 200:
                logger.debug(f"✅ طلب {endpoint} ناجح (Status: {response.status_code})")
                
                # حفظ الكوكيز بعد الطلبات الناجحة
                if endpoint != "signin":  # لا نحفظ بعد تسجيل الدخول مباشرة
                    self._save_cookies()
                    
                return response, response_data
            else:
                error_type = self._detect_error_type(response.status_code, response_data)
                error_msg = self._extract_error_message(response_data, error_type)
                
                logger.error(f"❌ فشل طلب {endpoint}: {error_msg} (Status: {response.status_code})")
                
                # تسجيل الخطأ في قاعدة البيانات
                db.log_error(
                    user_id='api',
                    error_type=error_type,
                    error_message=error_msg,
                    api_endpoint=endpoint,
                    request_data=json.dumps(request_data, ensure_ascii=False),
                    response_data=json.dumps(response_data, ensure_ascii=False, default=str)
                )
                
                return response, {'error': error_msg, 'status_code': response.status_code}
                
        except requests.exceptions.Timeout:
            error_msg = "⏱️ انتهت مهلة الاتصال بالخادم (30 ثانية)"
            logger.error(f"❌ {error_msg} - {endpoint}")
            
            db.log_error(
                user_id='api',
                error_type='timeout_error',
                error_message=error_msg,
                api_endpoint=endpoint
            )
            
            return None, {'error': error_msg}
            
        except requests.exceptions.ConnectionError:
            error_msg = "🔌 فشل الاتصال بالخادم"
            logger.error(f"❌ {error_msg} - {endpoint}")
            
            db.log_error(
                user_id='api',
                error_type='connection_error',
                error_message=error_msg,
                api_endpoint=endpoint
            )
            
            return None, {'error': error_msg}
            
        except Exception as e:
            error_msg = f"❌ خطأ غير متوقع: {str(e)}"
            logger.error(f"{error_msg} - {endpoint}")
            
            db.log_error(
                user_id='api',
                error_type='unexpected_error',
                error_message=error_msg,
                api_endpoint=endpoint,
                stack_trace=traceback.format_exc()
            )
            
            return None, {'error': error_msg}
    
    def _detect_error_type(self, status_code: int, response_data: Dict) -> str:
        """كشف نوع الخطأ"""
        if status_code == 401:
            return "authentication_error"
        elif status_code == 403:
            return "access_denied"
        elif status_code == 429:
            return "rate_limit"
        elif status_code >= 500:
            return "server_error"
        
        # تحليل محتوى الرد
        response_text = json.dumps(response_data).lower()
        
        if 'captcha' in response_text or 'cloudflare' in response_text:
            return "captcha_blocked"
        elif 'login' in response_text or 'password' in response_text:
            return "login_failed"
        elif 'insufficient' in response_text or 'balance' in response_text:
            return "insufficient_balance"
        elif 'not found' in response_text:
            return "not_found"
        elif 'already exists' in response_text:
            return "already_exists"
        
        return "api_error"
    
    def _extract_error_message(self, response_data: Dict, error_type: str) -> str:
        """استخراج رسالة الخطأ"""
        
        # إذا كان هناك خطأ مباشر
        if isinstance(response_data, dict):
            if 'error' in response_data:
                return str(response_data['error'])
            
            if 'message' in response_data:
                return str(response_data['message'])
            
            # محاولة استخراج من الإشعارات
            if 'notification' in response_data:
                notifications = response_data['notification']
                if isinstance(notifications, list) and notifications:
                    first_notification = notifications[0]
                    if isinstance(first_notification, dict) and 'content' in first_notification:
                        return str(first_notification['content'])
        
        # رسائل مخصصة بناءً على نوع الخطأ
        error_messages = {
            'authentication_error': "❌ فشل المصادقة: بيانات تسجيل الدخول غير صحيحة أو انتهت صلاحية الجلسة",
            'access_denied': "⛔ تم رفض الوصول: ليس لديك صلاحية للوصول إلى هذا المورد",
            'rate_limit': "🚫 تجاوزت الحد المسموح من الطلبات، يرجى الانتظار قليلاً",
            'server_error': "⚡ خطأ في الخادم الداخلي، يرجى المحاولة لاحقاً",
            'captcha_blocked': "🛡️ تم حظر الطلب بواسطة نظام الحماية (CAPTCHA/Cloudflare)",
            'login_failed': "🔐 فشل تسجيل الدخول: تحقق من اسم المستخدم وكلمة المرور",
            'insufficient_balance': "💸 رصيد غير كافي لإتمام العملية",
            'not_found': "🔍 المورد المطلوب غير موجود",
            'already_exists': "⚠️ المورد موجود مسبقاً",
            'api_error': "⚠️ حدث خطأ في واجهة برمجة التطبيقات"
        }
        
        return error_messages.get(error_type, "⚠️ حدث خطأ غير معروف")
    
    def login(self) -> Dict:
        """تسجيل الدخول إلى حساب الوكيل"""
        
        # التحقق من بيانات الاعتماد
        if not config.AGENT_USERNAME or not config.AGENT_PASSWORD:
            error_msg = "❌ بيانات تسجيل الدخول غير مضبوطة في إعدادات التطبيق"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        # التحقق من تكرار محاولات تسجيل الدخول
        current_time = time.time()
        if self.login_attempts >= 3 and current_time - self.last_login_time < 300:  # 5 دقائق
            error_msg = "🚫 تم تجاوز عدد محاولات تسجيل الدخول المسموح بها، يرجى الانتظار 5 دقائق"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        payload = {
            "username": config.AGENT_USERNAME,
            "password": config.AGENT_PASSWORD
        }
        
        logger.info(f"🔐 محاولة تسجيل الدخول باسم: {config.AGENT_USERNAME}")
        
        response, data = self._make_request("POST", "signin", json=payload)
        
        self.login_attempts += 1
        self.last_login_time = current_time
        
        if response is None:
            return {'success': False, 'error': data.get('error', 'فشل الاتصال بالخادم')}
        
        # تحقق من نجاح تسجيل الدخول
        if isinstance(data, dict) and data.get("result") is True:
            self.is_logged_in = True
            self.login_attempts = 0  # إعادة تعيين عداد المحاولات
            
            # حفظ الكوكيز الجديدة
            self._save_cookies()
            
            logger.info("✅ تم تسجيل الدخول بنجاح إلى حساب الوكيل")
            return {'success': True, 'data': data}
        else:
            error_msg = data.get('error', 'فشل تسجيل الدخول: رد غير متوقع من الخادم')
            
            # تسجيل الخطأ بتفاصيل أكثر
            error_details = {
                'error': error_msg,
                'attempt': self.login_attempts,
                'username': config.AGENT_USERNAME,
                'status_code': response.status_code if response else 'N/A'
            }
            
            logger.error(f"❌ فشل تسجيل الدخول: {error_msg}")
            
            return {'success': False, 'error': error_msg, 'details': error_details}
    
    def ensure_login(self) -> bool:
        """التأكد من تسجيل الدخول مع إعادة المحاولة"""
        if self.is_logged_in:
            # التحقق من صلاحية الجلسة
            try:
                # طلب اختباري للتحقق من الجلسة
                test_response, test_data = self._make_request("POST", "statistics", json={"page": 1, "pageSize": 1})
                
                if test_response and test_response.status_code == 200:
                    return True
                else:
                    self.is_logged_in = False
                    logger.warning("⚠️ انتهت صلاحية الجلسة، جارٍ إعادة تسجيل الدخول...")
            except:
                self.is_logged_in = False
        
        # محاولة تسجيل الدخول
        result = self.login()
        
        if result.get('success'):
            return True
        else:
            error_msg = result.get('error', 'فشل تسجيل الدخول')
            logger.error(f"❌ فشل التأكد من تسجيل الدخول: {error_msg}")
            return False
    
    def create_player(self, login: str, password: str) -> Dict:
        """إنشاء لاعب جديد"""
        
        # التحقق من تسجيل الدخول أولاً
        if not self.ensure_login():
            return {
                'success': False,
                'error': '❌ فشل إنشاء الحساب: لا يمكن الوصول إلى واجهة برمجة التطبيقات'
            }
        
        if not config.PARENT_ID:
            return {
                'success': False,
                'error': '❌ فشل إنشاء الحساب: Parent ID غير مضبوط'
            }
        
        # إنشاء إيميل فريد
        email = f"{login}@TSA.com"
        
        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": config.PARENT_ID,
                "login": login
            }
        }
        
        logger.info(f"👤 محاولة إنشاء لاعب جديد: {login}")
        
        response, data = self._make_request("POST", "create_player", json=payload)
        
        if response is None:
            return {'success': False, 'error': '❌ فشل الاتصال بخادم إنشاء الحسابات'}
        
        if isinstance(data, dict) and data.get("result") is True:
            # الحصول على معرف اللاعب
            player_id = self.get_player_id(login)
            
            logger.info(f"✅ تم إنشاء اللاعب بنجاح: {login} (ID: {player_id})")
            
            return {
                'success': True,
                'player_id': player_id,
                'email': email,
                'login': login,
                'data': data
            }
        else:
            error_msg = data.get('error', '❌ فشل إنشاء الحساب: رد غير متوقع من الخادم')
            
            # تحليل الخطأ
            if 'already exists' in error_msg.lower() or 'موجود' in error_msg:
                error_msg = "⚠️ اسم المستخدم موجود مسبقاً، يرجى اختيار اسم آخر"
            elif 'invalid' in error_msg.lower():
                error_msg = "⚠️ بيانات غير صالحة، تحقق من صحة المدخلات"
            
            logger.error(f"❌ فشل إنشاء اللاعب {login}: {error_msg}")
            
            return {'success': False, 'error': error_msg}
    
    def get_player_id(self, login: str) -> Optional[str]:
        """الحصول على معرف اللاعب"""
        try:
            if not self.ensure_login():
                return None
            
            payload = {
                "page": 1,
                "pageSize": 100,
                "filter": {"login": login}
            }
            
            response, data = self._make_request("POST", "statistics", json=payload)
            
            if response is None or not isinstance(data, dict):
                return None
            
            result = data.get("result", {})
            records = result.get("records", [])
            
            for record in records:
                if isinstance(record, dict) and record.get("username") == login:
                    player_id = record.get("playerId")
                    logger.debug(f"🔍 تم العثور على معرف اللاعب {login}: {player_id}")
                    return player_id
            
            logger.warning(f"⚠️ لم يتم العثور على معرف للاعب: {login}")
            return None
            
        except Exception as e:
            logger.error(f"❌ فشل الحصول على معرف اللاعب {login}: {str(e)}")
            return None
    
    def deposit(self, player_id: str, amount: float) -> Dict:
        """إيداع رصيد للاعب"""
        
        if not self.ensure_login():
            return {
                'success': False,
                'error': '❌ فشل الإيداع: لا يمكن الوصول إلى واجهة برمجة التطبيقات'
            }
        
        if amount < config.APP_CONFIG["min_amount"]:
            return {
                'success': False,
                'error': f'❌ المبلغ أقل من الحد الأدنى ({config.APP_CONFIG["min_amount"]} NSP)'
            }
        
        payload = {
            "amount": amount,
            "comment": None,
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }
        
        logger.info(f"💰 محاولة إيداع {amount} NSP للاعب {player_id}")
        
        response, data = self._make_request("POST", "deposit", json=payload)
        
        if response is None:
            return {'success': False, 'error': '❌ فشل الاتصال بخادم الإيداع'}
        
        if isinstance(data, dict) and data.get("result") is True:
            logger.info(f"✅ تم الإيداع بنجاح: {amount} NSP للاعب {player_id}")
            return {'success': True, 'data': data}
        else:
            error_msg = data.get('error', '❌ فشل الإيداع: رد غير متوقع من الخادم')
            
            # تحليل أخطاء الإيداع الشائعة
            if 'insufficient' in error_msg.lower():
                error_msg = "💸 رصيد وكيل Ichancy غير كافي"
            elif 'not found' in error_msg.lower():
                error_msg = "🔍 اللاعب غير موجود أو معرفه غير صحيح"
            
            logger.error(f"❌ فشل إيداع {amount} NSP للاعب {player_id}: {error_msg}")
            
            return {'success': False, 'error': error_msg}
    
    def withdraw(self, player_id: str, amount: float) -> Dict:
        """سحب رصيد من اللاعب"""
        
        if not self.ensure_login():
            return {
                'success': False,
                'error': '❌ فشل السحب: لا يمكن الوصول إلى واجهة برمجة التطبيقات'
            }
        
        if amount < config.APP_CONFIG["min_amount"]:
            return {
                'success': False,
                'error': f'❌ المبلغ أقل من الحد الأدنى ({config.APP_CONFIG["min_amount"]} NSP)'
            }
        
        # التحقق من رصيد اللاعب أولاً
        balance_result = self.get_balance(player_id)
        if not balance_result.get('success'):
            return {
                'success': False,
                'error': f'❌ فشل التحقق من الرصيد: {balance_result.get("error", "خطأ غير معروف")}'
            }
        
        current_balance = balance_result.get('balance', 0)
        if current_balance < amount:
            return {
                'success': False,
                'error': f'❌ رصيد اللاعب غير كافي. الرصيد الحالي: {current_balance} NSP'
            }
        
        payload = {
            "amount": -amount,  # سالب للسحب
            "comment": None,
            "playerId": player_id,
            "currencyCode": "NSP",
            "currency": "NSP",
            "moneyStatus": 5
        }
        
        logger.info(f"💳 محاولة سحب {amount} NSP من اللاعب {player_id}")
        
        response, data = self._make_request("POST", "withdraw", json=payload)
        
        if response is None:
            return {'success': False, 'error': '❌ فشل الاتصال بخادم السحب'}
        
        if isinstance(data, dict) and data.get("result") is True:
            logger.info(f"✅ تم السحب بنجاح: {amount} NSP من اللاعب {player_id}")
            return {'success': True, 'data': data}
        else:
            error_msg = data.get('error', '❌ فشل السحب: رد غير متوقع من الخادم')
            
            # تحليل أخطاء السحب الشائعة
            if 'insufficient' in error_msg.lower():
                error_msg = "💸 رصيد اللاعب غير كافي للسحب"
            elif 'not found' in error_msg.lower():
                error_msg = "🔍 اللاعب غير موجود أو معرفه غير صحيح"
            elif 'limit' in error_msg.lower():
                error_msg = "🚫 تجاوز الحد المسموح للسحب"
            
            logger.error(f"❌ فشل سحب {amount} NSP من اللاعب {player_id}: {error_msg}")
            
            return {'success': False, 'error': error_msg}
    
    def get_balance(self, player_id: str) -> Dict:
        """الحصول على رصيد اللاعب"""
        
        if not self.ensure_login():
            return {
                'success': False,
                'error': '❌ فشل جلب الرصيد: لا يمكن الوصول إلى واجهة برمجة التطبيقات',
                'balance': 0
            }
        
        payload = {"playerId": str(player_id)}
        
        logger.debug(f"📊 محاولة جلب رصيد اللاعب: {player_id}")
        
        response, data = self._make_request("POST", "balance", json=payload)
        
        if response is None:
            return {
                'success': False,
                'error': '❌ فشل الاتصال بخادم الرصيد',
                'balance': 0
            }
        
        if isinstance(data, dict):
            result = data.get("result", [])
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict):
                    balance = result[0].get("balance", 0)
                    logger.debug(f"✅ رصيد اللاعب {player_id}: {balance} NSP")
                    return {'success': True, 'balance': balance, 'data': data}
        
        error_msg = data.get('error', '❌ فشل تحليل بيانات الرصيد')
        logger.error(f"❌ فشل جلب رصيد اللاعب {player_id}: {error_msg}")
        
        return {'success': False, 'error': error_msg, 'balance': 0}
    
    def check_player_exists(self, login: str) -> bool:
        """التحقق من وجود اللاعب"""
        try:
            if not self.ensure_login():
                return False
            
            payload = {
                "page": 1,
                "pageSize": 100,
                "filter": {"login": login}
            }
            
            response, data = self._make_request("POST", "statistics", json=payload)
            
            if response is None or not isinstance(data, dict):
                return False
            
            result = data.get("result", {})
            records = result.get("records", [])
            
            for record in records:
                if isinstance(record, dict) and record.get("username") == login:
                    logger.debug(f"✅ اللاعب موجود: {login}")
                    return True
            
            logger.debug(f"❌ اللاعب غير موجود: {login}")
            return False
            
        except Exception as e:
            logger.error(f"❌ فشل التحقق من وجود اللاعب {login}: {str(e)}")
            return False
    
    def reset_session(self):
        """إعادة تعيين الجلسة"""
        self.session = self._create_session()
        self._setup_headers()
        self.is_logged_in = False
        self.login_attempts = 0
        
        # مسح الكوكيز المخزنة
        if self.redis_client:
            self.redis_client.delete(config.APP_CONFIG["cookie_key"])
        
        logger.info("🔄 تم إعادة تعيين جلسة API")

# إنشاء نسخة وحيدة من API
api = IchancyAPI()

if __name__ == "__main__":
    # اختبار واجهة برمجة التطبيقات
    print("🔍 اختبار واجهة Ichancy API...")
    
    try:
        # اختبار تسجيل الدخول
        login_result = api.login()
        
        if login_result.get('success'):
            print("✅ تسجيل الدخول إلى Ichancy ناجح")
            
            # اختبار جلب الرصيد (إذا كان هناك لاعب معروف)
            test_player_id = "test_player"
            balance_result = api.get_balance(test_player_id)
            
            if balance_result.get('success'):
                print(f"✅ جلب الرصيد ناجح: {balance_result.get('balance')} NSP")
            else:
                print(f"⚠️ جلب الرصيد فشل: {balance_result.get('error')}")
            
        else:
            print(f"❌ فشل تسجيل الدخول: {login_result.get('error')}")
            
            # عرض التفاصيل إذا وجدت
            if 'details' in login_result:
                print(f"   التفاصيل: {login_result['details']}")
    
    except Exception as e:
        print(f"❌ فشل اختبار API: {str(e)}")
        import traceback
        traceback.print_exc()
