"""CourseVille login forms and alpha OAuth client discovery."""
import re
import requests
from bs4 import BeautifulSoup

class LoginSession:

    def __init__(self, username=None, password=None):
        self.session = requests.Session()
        self.username = username
        self.password = password
        self._configure_session()

    def _configure_session(self):
        """Configure session-wide headers"""
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36', 'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'identity', 'Upgrade-Insecure-Requests': '1', 'has_js': '1', 'Connection': 'keep-alive'})

    def _get_homepage(self):
        """Make initial request to get session cookies"""
        response = self.session.get('https://www.mycourseville.com')
        response.raise_for_status()
        return response

    def _get_login_page(self):
        """GET login page and handle response"""
        login_url = 'https://www.mycourseville.com/api/oauth/authorize?response_type=code&client_id=mycourseville.com&redirect_uri=https://www.mycourseville.com&login_page=itchula'
        response = self.session.get(login_url)
        response.raise_for_status()
        if 'Content-Type' in response.headers and 'charset=' in response.headers['Content-Type']:
            response.encoding = response.headers['Content-Type'].split('charset=')[-1]
        else:
            response.encoding = 'utf-8'
        return response

    def _extract_csrf_token(self, login_page_response):
        """Extract CSRF token from login page HTML"""
        soup = BeautifulSoup(login_page_response.text, 'html.parser')
        token_input = soup.find('input', {'name': '_token'})
        if not token_input:
            return None
        token = token_input.get('value')
        return token

    def _perform_login(self, csrf_token):
        """Perform login with credentials and CSRF token"""
        login_data = {'_token': csrf_token, 'username': self.username, 'password': self.password, 'remember': 'on'}
        response = self.session.post('https://www.mycourseville.com/api/chulalogin', data=login_data, allow_redirects=True)
        return response

class AlphaDiscovery(LoginSession):

    def get_client_id(self):
        page = self.session.get('https://alpha.mycourseville.com/')
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')
        script_tag = soup.find('script', src=lambda s: s and '/assets/index-' in s)
        if not script_tag:
            raise RuntimeError('alpha_bundle_missing')
        js_src = script_tag['src']
        js_url = js_src if js_src.startswith('http') else 'https://alpha.mycourseville.com' + js_src
        response = self.session.get(js_url)
        response.raise_for_status()
        js_code = response.text
        match = re.search('https?:\\/\\/[^\\s"\\\']+client_id=([a-zA-Z0-9_-]{20,})', js_code)
        if match:
            return match.group(1)
        else:
            raise RuntimeError('alpha_client_id_missing')
