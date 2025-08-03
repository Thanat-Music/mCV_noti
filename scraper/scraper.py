import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
import re
import json

class CVScraper:
    """A class to scrape Courseville website for login and session management."""
    def __init__(self,username=None, password=None):
        self.session = requests.Session()
        self.username = username
        self.password = password
        self._configure_session()

    def _configure_session(self):
        """Configure session-wide headers"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',
            'Upgrade-Insecure-Requests': '1',
            'has_js':'1',
            'Connection': 'keep-alive'
        })
    

    def _get_cookie(self, is_dict=False):
        """Extract cookies from session object."""
        cookie_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
        if is_dict:
            return cookie_dict
        return "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
    
    def _get_homepage(self,show = False):
        """Make initial request to get session cookies"""
        if show:
            print("Fetching homepage...")
        response = self.session.get("https://www.mycourseville.com")
        response.raise_for_status()
        if show:
            print(f"Initial Cookies: {self._get_cookie(response)}\n--------------------------")
        return response
    
    def _get_login_page(self,show = False):
        """GET login page and handle response"""
        login_url = "https://www.mycourseville.com/api/oauth/authorize?response_type=code&client_id=mycourseville.com&redirect_uri=https://www.mycourseville.com&login_page=itchula"
        if show:
            print("Fetching login page...")
        response = self.session.get(login_url)
        response.raise_for_status()
        
        # Handle encoding issues
        if 'Content-Type' in response.headers and 'charset=' in response.headers['Content-Type']:
            response.encoding = response.headers['Content-Type'].split('charset=')[-1]
        else:
            response.encoding = 'utf-8'  # Fallback to UTF-8
        if show:    
            print(f"Login Page Status: {response.status_code}")
            print(f"Login Page Cookies: {self._get_cookie(response)}")
            print("--------------------------")
        return response
    
    def _extract_csrf_token(self, login_page_response,show = False):
        """Extract CSRF token from login page HTML"""
        soup = BeautifulSoup(login_page_response.text, 'html.parser')
        token_input = soup.find('input', {'name': '_token'})
        
        if not token_input:
            print("Error: Could not find CSRF token in login page!")
            print("status code:", login_page_response.status_code)
            return None

        token = token_input.get('value')
        if show:
            print(f"Extracted CSRF Token: {token}\n--------------------------")
        return token
    
    def _perform_login(self, csrf_token,show = False):
        """Perform login with credentials and CSRF token"""
        login_data = {
            '_token': csrf_token,
            'username': self.username,
            'password': self.password,
            'remember': 'on'
        }
        if show:
            print("Attempting login...")
            print(f"Login Data: {login_data}")
        response = self.session.post(
            "https://www.mycourseville.com/api/chulalogin",
            data=login_data,
            allow_redirects=True
        )
        return response
    
    def _verify_login(self,show = False):
        """Verify successful login by checking protected page"""
        dashboard = self.session.get("https://www.mycourseville.com/")
        if "2024" in dashboard.text.lower():
            if show:
                print("Login Verified\n--------------------------")
            return True
        if show:
            print("Login Verification Failed\n--------------------------")
        return False
    
    def run(self,show = False):
        """Main method to execute the scraping process"""
        try:
            if show:
                print("")
            # Step 1: Initial request
            self._get_homepage(show)
            login_page = self._get_login_page(show)
            token = self._extract_csrf_token(login_page,show)
            if not token:
                return False
            # Step 2: Perform login
            login_response = self._perform_login(token,show)
            if login_response.status_code == 200:
                if show:
                    print(f"Final Cookies: {self._get_cookie(True)}")
                    print("\nLogin successful!")
                return self._verify_login(show)
            else:
                if show:
                    print(f"\nLogin failed! Status: {login_response.status_code}")
                return False  
        except requests.exceptions.RequestException as e:
            print(f"\nError occurred: {str(e)}")
            return False
    
class CVaScraper(CVScraper):
    """A class to scrape Courseville website for course information."""
    def __init__(self,username, password, show=False):
        super().__init__(username=username, password=password)
        self.run(show)
        self.client_id = self.get_client_id(show)
        token = self.grant_token(show)
        self.auth_token = token['access_token']
        self.refresh_token = token['refresh_token']
        
    def _update_session_headers(self,auth_token=None):
        self.session.headers.update({
            'Authorization': f'Bearer {auth_token}',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Connection': 'keep-alive',
        })
        
    
    def get_client_id(self,show = False):
        js_url = "https://alpha.mycourseville.com/assets/index-BT6DwrJv.js"
        #Download the JS file
        response = self.session.get(js_url)
        if show:
            print(f"Response status code: {response.status_code}")
        js_code = response.text

        #Search for client_id pattern
        match = re.search(r'https?:\/\/[^\s"\']+client_id=([a-zA-Z0-9_-]{20,})', js_code)
        if match:
            return match.group(1)
        else:
            raise Exception("!!!ALERT!!! client_id not found in script.")
        
    @staticmethod
    def get_body_length(body):
        return len(str(body).encode("utf-8"))

    def grant_token(self,show = False):
        """Grant token to access Courseville API"""
        if show: print("Granting token...")
        url = f"https://www.mycourseville.com/api/oauth/authorize?response_type=code&client_id={self.client_id}&redirect_uri=https://alpha.mycourseville.com/&state=/course"
        response = self.session.get(url,allow_redirects=False)
        if response.status_code != 302:
            raise Exception(f"!!!ALERT!!! code extracttion Error: {response.status_code}")
        location = response.headers['Location']
        code = re.search(r'[?&]code=([^&]+)', location).group(1)    # Extract the code from the URL
        if show: print(f"Code: {code}")
        # Make a POST request to get the token
        api_url = "https://api.alpha.mycourseville.com/auth/login"
        body = {"code": code}
        headers = {
            'Host': 'api.alpha.mycourseville.com',
            'Content-Length': str(self.get_body_length(body)),
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json'}
        if show: print(f"headers: {headers}")
        token = requests.post(api_url,headers=headers, json=body)
        if token.status_code == 200:
            token_data = json.loads(token.text)
            if show: print(f"Token: {token_data}")
            return token_data
        else: 
            raise Exception(f"!!!ALERT!!! token granting Error: {token.status_code} \ntext: {token.text}")
    
    def query_assignment(self,semester = 1, year = 2023, filter ="ALL"):
        """Query assignment data from Courseville API."""
        playload = {
            "query":"query AssignmentSummaryPageQuery($semester: String! $year: String! $filter: AssignmentFilter!) {...AssignmentSummaryFragment_bZQ9B}\
                    fragment AssignmentSummaryFragment_bZQ9B on Query {\
                    me {myCoursesBySemester(semester: $semester, year: $year) \
                    {\
                        student {\
                            courseID title courseNumber courseYear thumbnail semester assignments(filter: $filter) \
                                {courseID id title type status outDate dueDate}}}}}",
            "variables":{"semester":semester,"year":year,"filter":filter}
            }
        headers = {'Authorization': f'Bearer {self.auth_token}',
                'Content-Type': 'application/json',
                'Content-Length': str(CVaScraper.get_body_length(playload))}

        data_res = self.session.post("https://api.alpha.mycourseville.com/query",headers=headers,json=playload)
        if data_res.status_code == 200:
            return data_res.json()
        else:
            raise Exception(f"!!!ALERT!!! query assignment Error: {data_res.status_code} \n text: {data_res.text}")

if __name__ == "__main__":
    scraper = CVaScraper("#", "#", show=True)
    print(scraper.get_client_id(True))
    scraper.grant_token(True)
    print(scraper.query_assignment(semester = 1, year = 2024, filter ="ALL"))
