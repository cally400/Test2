
# api/captcha_solver.py
import time
import random
import logging
import json
from typing import Dict, Optional, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import config
from database import db

logger = logging.getLogger(__name__)

class CaptchaSolver:
    """نظام متقدم لتخطي أنظمة الحماية (CAPTCHA/Cloudflare)"""
    
    def __init__(self):
        self.session = self._create_session()
        self.captcha_attempts = 0
        self.last_captcha_time = 0
        self.redis_client = config.get_redis_client()
        self._setup_headers()
    
    def _create_session(self):
        """إنشاء جلسة مع إعدادات متقدمة"""
        session = requests.Session()
        
        # إعدادات إعادة المحاولة المتقدمة
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[403, 408, 429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            respect_retry_after_header=True
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=100,
            pool_maxsize=100
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _setup_headers(self):
        """إعداد رؤوس HTTP متقدمة"""
        user_agent = random.choice(config.USER_AGENTS)
        
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Sec-CH-UA': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
        })
    
    def _human_like_delay(self, min_seconds: float = 2.0, max_seconds: float = 5.0):
        """تأخير عشوائي يشبه السلوك البشري"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
        logger.debug(f"⏳ تأخير لمدة {delay:.1f} ثانية")
    
    def _rotate_user_agent(self):
        """تغيير User Agent بشكل عشوائي"""
        new_agent = random.choice(config.USER_AGENTS)
        self.session.headers.update({'User-Agent': new_agent})
        logger.debug(f"🔄 تغيير User-Agent إلى: {new_agent[:50]}...")
    
    def detect_protection_type(self, response: requests.Response) -> str:
        """كشف نوع نظام الحماية"""
        try:
            content = response.text.lower()
            status_code = response.status_code
            
            logger.debug(f"🔍 تحليل الرد (Status: {status_code})")
            
            # Cloudflare Detection
            if status_code == 403 and ('cloudflare' in content or 'cf-ray' in response.headers):
                return 'cloudflare'
            
            # CAPTCHA Detection
            if 'captcha' in content or 'recaptcha' in content or 'g-recaptcha' in content:
                if 'hcaptcha' in content:
                    return 'hcaptcha'
                elif 'recaptcha' in content:
                    return 'recaptcha'
                else:
                    return 'basic_captcha'
            
            # DDoS Protection
            if 'ddos' in content or 'security' in content or 'protection' in content:
                return 'ddos_protection'
            
            # Rate Limiting
            if status_code == 429 or 'rate limit' in content or 'too many requests' in content:
                return 'rate_limit'
            
            # Access Denied
            if status_code == 403:
                return 'access_denied'
            
            # Browser Verification
            if 'browser' in content and 'verify' in content:
                return 'browser_verification'
            
            # JavaScript Challenge
            if '<script>' in content and 'challenge' in content:
                return 'js_challenge'
            
            return 'unknown'
            
        except Exception as e:
            logger.error(f"❌ فشل كشف نوع الحماية: {str(e)}")
            return 'unknown'
    
    def extract_protection_details(self, response: requests.Response, protection_type: str) -> Dict:
        """استخراج تفاصيل نظام الحماية"""
        details = {
            'type': protection_type,
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'content_length': len(response.text),
            'timestamp': time.time()
        }
        
        try:
            content = response.text.lower()
            
            if protection_type == 'cloudflare':
                # استخراج معلومات Cloudflare
                if 'cf-ray' in response.headers:
                    details['cf_ray'] = response.headers['cf-ray']
                
                if 'cf-chl-bypass' in content:
                    details['has_bypass'] = True
                
                # البحث عن عناصر التحدي
                if 'challenge-form' in content:
                    details['has_challenge_form'] = True
                
                if 'jschl-answer' in content:
                    details['has_jschl_challenge'] = True
            
            elif protection_type in ['recaptcha', 'hcaptcha']:
                # استخراج معلومات CAPTCHA
                if 'sitekey' in content:
                    # البحث عن sitekey
                    import re
                    sitekey_match = re.search(r'sitekey\s*[:=]\s*["\']([^"\']+)["\']', content)
                    if sitekey_match:
                        details['sitekey'] = sitekey_match.group(1)
            
            elif protection_type == 'rate_limit':
                # استخراج معلومات التقييد
                if 'retry-after' in response.headers:
                    details['retry_after'] = response.headers['retry-after']
            
        except Exception as e:
            logger.error(f"❌ فشل استخراج تفاصيل الحماية: {str(e)}")
        
        return details
    
    def log_captcha_attempt(self, url: str, protection_type: str, success: bool, details: Dict = None):
        """تسجيل محاولة تخطي الحماية"""
        try:
            error_data = {
                'user_id': 'captcha_solver',
                'error_type': f'captcha_{protection_type}',
                'error_message': f'محاولة تخطي {protection_type}: {"نجاح" if success else "فشل"}',
                'api_endpoint': url,
                'request_data': json.dumps({
                    'protection_type': protection_type,
                    'timestamp': time.time(),
                    'attempt': self.captcha_attempts
                }, ensure_ascii=False),
                'response_data': json.dumps(details or {}, ensure_ascii=False, default=str)
            }
            
            db.log_error(**error_data)
            
            if success:
                logger.info(f"✅ تم تخطي {protection_type} بنجاح")
            else:
                logger.warning(f"⚠️ فشل تخطي {protection_type}")
                
        except Exception as e:
            logger.error(f"❌ فشل تسجيل محاولة CAPTCHA: {str(e)}")
    
    def bypass_cloudflare(self, url: str, max_retries: int = 3) -> Tuple[Optional[requests.Response], str]:
        """محاولة تخطي حماية Cloudflare"""
        
        # التحقق من تكرار المحاولات
        current_time = time.time()
        if self.captcha_attempts >= 5 and current_time - self.last_captcha_time < 300:
            error_msg = "🚫 تجاوزت الحد المسموح من محاولات تخطي الحماية، يرجى الانتظار 5 دقائق"
            logger.error(error_msg)
            return None, error_msg
        
        self.captcha_attempts += 1
        self.last_captcha_time = current_time
        
        logger.info(f"🛡️ محاولة تخطي Cloudflare (المحاولة {self.captcha_attempts}/{max_retries})")
        
        for attempt in range(max_retries):
            try:
                # تغيير User Agent قبل كل محاولة
                self._rotate_user_agent()
                
                # تأخير عشوائي بين المحاولات
                if attempt > 0:
                    wait_time = random.uniform(10, 30)
                    logger.info(f"⏳ الانتظار {wait_time:.1f} ثانية قبل المحاولة التالية...")
                    time.sleep(wait_time)
                
                # إرسال طلب GET مع إعدادات خاصة
                self._human_like_delay(3, 7)
                
                logger.debug(f"🌐 إرسال طلب إلى: {url} (المحاولة {attempt + 1})")
                
                response = self.session.get(
                    url,
                    timeout=45,
                    allow_redirects=True,
                    headers={
                        **self.session.headers,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                    }
                )
                
                # تحليل الرد
                protection_type = self.detect_protection_type(response)
                details = self.extract_protection_details(response, protection_type)
                
                logger.debug(f"📊 نوع الحماية المكتشف: {protection_type}")
                
                if protection_type == 'cloudflare':
                    if response.status_code == 200:
                        # نجاح تخطي Cloudflare
                        self.log_captcha_attempt(url, protection_type, True, details)
                        logger.info("✅ تم تخطي Cloudflare بنجاح!")
                        return response, "تم تخطي Cloudflare بنجاح"
                    else:
                        # فشل التخطي
                        error_msg = f"❌ فشل تخطي Cloudflare (Status: {response.status_code})"
                        logger.warning(error_msg)
                        
                        # تحليل محتوى الخطأ
                        if 'captcha' in response.text.lower():
                            error_msg = "🛡️ مطلوب حل CAPTCHA يدوياً"
                        elif 'access denied' in response.text.lower():
                            error_msg = "⛔ تم رفض الوصول من قبل Cloudflare"
                        
                        self.log_captcha_attempt(url, protection_type, False, details)
                        
                        if attempt < max_retries - 1:
                            continue
                        else:
                            return None, error_msg
                
                elif protection_type in ['recaptcha', 'hcaptcha']:
                    error_msg = f"🛡️ مطلوب حل {protection_type.upper()} يدوياً"
                    logger.error(error_msg)
                    self.log_captcha_attempt(url, protection_type, False, details)
                    return None, error_msg
                
                elif protection_type == 'rate_limit':
                    error_msg = "🚫 تجاوزت الحد المسموح من الطلبات، يرجى الانتظار"
                    logger.error(error_msg)
                    
                    # استخراج وقت الانتظار
                    retry_after = details.get('retry_after', '60')
                    error_msg += f" {retry_after} ثانية"
                    
                    self.log_captcha_attempt(url, protection_type, False, details)
                    return None, error_msg
                
                elif response.status_code == 200:
                    # لا يوجد حماية أو تم تخطيها
                    logger.info("✅ تم الوصول إلى الموقع بنجاح (بدون حماية)")
                    return response, "تم الوصول بنجاح"
                
                else:
                    error_msg = f"❌ فشل الوصول (Status: {response.status_code})"
                    logger.error(error_msg)
                    self.log_captcha_attempt(url, protection_type, False, details)
                    
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return None, error_msg
                    
            except requests.exceptions.Timeout:
                error_msg = f"⏱️ انتهت مهلة المحاولة {attempt + 1}"
                logger.error(error_msg)
                
                if attempt < max_retries - 1:
                    continue
                else:
                    return None, "انتهت مهلة جميع المحاولات"
                    
            except requests.exceptions.ConnectionError:
                error_msg = f"🔌 فشل الاتصال في المحاولة {attempt + 1}"
                logger.error(error_msg)
                
                if attempt < max_retries - 1:
                    continue
                else:
                    return None, "فشل الاتصال بعد جميع المحاولات"
                    
            except Exception as e:
                error_msg = f"❌ خطأ غير متوقع في المحاولة {attempt + 1}: {str(e)}"
                logger.error(error_msg)
                
                if attempt < max_retries - 1:
                    continue
                else:
                    return None, f"خطأ غير متوقع: {str(e)}"
        
        return None, "فشل جميع محاولات تخطي الحماية"
    
    def solve_js_challenge(self, response: requests.Response) -> Optional[requests.Response]:
        """حل تحديات JavaScript البسيطة"""
        try:
            content = response.text
            
            # البحث عن تحديات JavaScript الشائعة
            if 'jschl-answer' in content:
                logger.info("🔧 محاولة حل تحدّي JavaScript...")
                
                # هذا مثال مبسط، في الواقع يحتاج إلى معالجة أكثر تعقيداً
                # يمكن استخدام libraries مثل cloudscraper هنا
                
                # محاكاة حل التحدي
                self._human_like_delay(5, 10)
                
                # إعادة إرسال الطلب بعد "حل" التحدي
                new_response = self.session.get(
                    response.url,
                    timeout=30,
                    headers=self.session.headers
                )
                
                if new_response.status_code == 200:
                    logger.info("✅ تم "حل" تحدّي JavaScript")
                    return new_response
            
            return None
            
        except Exception as e:
            logger.error(f"❌ فشل حل تحدّي JavaScript: {str(e)}")
            return None
    
    def get_cookies_dict(self) -> Dict:
        """الحصول على الكوكيز كقاموس"""
        return requests.utils.dict_from_cookiejar(self.session.cookies)
    
    def update_cookies(self, cookies_dict: Dict):
        """تحديث كوكيز الجلسة"""
        self.session.cookies.update(cookies_dict)
    
    def clear_cookies(self):
        """مسح جميع الكوكيز"""
        self.session.cookies.clear()
        logger.debug("🧹 تم مسح كوكيز الجلسة")
    
    def test_protection_bypass(self, url: str = None) -> Dict:
        """اختبار قدرة النظام على تخطي الحماية"""
        test_url = url or config.ORIGIN
        
        logger.info(f"🧪 اختبار تخطي الحماية لـ: {test_url}")
        
        result = {
            'url': test_url,
            'timestamp': time.time(),
            'success': False,
            'protection_type': 'unknown',
            'message': '',
            'details': {}
        }
        
        try:
            # محاولة الوصول العادي أولاً
            logger.debug("🔍 محاولة الوصول العادي...")
            normal_response = self.session.get(test_url, timeout=15)
            
            protection_type = self.detect_protection_type(normal_response)
            result['protection_type'] = protection_type
            
            if protection_type in ['cloudflare', 'recaptcha', 'hcaptcha']:
                logger.info(f"🛡️ تم اكتشاف {protection_type}، جارٍ محاولة التخطي...")
                
                bypass_response, message = self.bypass_cloudflare(test_url, max_retries=2)
                
                if bypass_response:
                    result['success'] = True
                    result['message'] = message
                    result['details'] = self.extract_protection_details(bypass_response, protection_type)
                else:
                    result['success'] = False
                    result['message'] = message
            
            elif normal_response.status_code == 200:
                result['success'] = True
                result['message'] = "الموقع قابل للوصول بدون حماية"
                result['details'] = {'status_code': 200}
            
            else:
                result['success'] = False
                result['message'] = f"فشل الوصول (Status: {normal_response.status_code})"
                result['details'] = {'status_code': normal_response.status_code}
        
        except Exception as e:
            result['success'] = False
            result['message'] = f"خطأ في الاختبار: {str(e)}"
            logger.error(f"❌ فشل اختبار الحماية: {str(e)}")
        
        # تسجيل نتيجة الاختبار
        db.log_error(
            user_id='system',
            error_type='protection_test',
            error_message=f"اختبار الحماية: {result['message']}",
            api_endpoint=test_url,
            request_data=json.dumps({'test_type': 'protection_bypass'}, ensure_ascii=False),
            response_data=json.dumps(result, ensure_ascii=False, default=str)
        )
        
        return result
    
    def get_session_info(self) -> Dict:
        """الحصول على معلومات الجلسة"""
        return {
            'user_agent': self.session.headers.get('User-Agent'),
            'cookies_count': len(self.session.cookies),
            'captcha_attempts': self.captcha_attempts,
            'last_attempt': self.last_captcha_time,
            'headers': dict(self.session.headers)
        }

# إنشاء نسخة وحيدة من محلل CAPTCHA
captcha_solver = CaptchaSolver()

if __name__ == "__main__":
    # اختبار محلل CAPTCHA
    print("🔍 اختبار نظام تخطي الحماية...")
    
    try:
        # اختبار الوصول إلى موقع Ichancy
        test_result = captcha_solver.test_protection_bypass(config.ORIGIN)
        
        print(f"\n📊 نتائج الاختبار:")
        print(f"   الموقع: {test_result['url']}")
        print(f"   النجاح: {'✅' if test_result['success'] else '❌'}")
        print(f"   نوع الحماية: {test_result['protection_type']}")
        print(f"   الرسالة: {test_result['message']}")
        
        if test_result['success']:
            print("\n🎉 النظام قادر على تخطي الحماية!")
        else:
            print(f"\n⚠️ يحتاج النظام إلى تحسينات: {test_result['message']}")
        
        # عرض معلومات الجلسة
        session_info = captcha_solver.get_session_info()
        print(f"\n📋 معلومات الجلسة:")
        print(f"   User-Agent: {session_info['user_agent'][:50]}...")
        print(f"   عدد الكوكيز: {session_info['cookies_count']}")
        print(f"   محاولات CAPTCHA: {session_info['captcha_attempts']}")
    
    except Exception as e:
        print(f"❌ فشل اختبار نظام الحماية: {str(e)}")
        import traceback
        traceback.print_exc()
