import requests
from bs4 import BeautifulSoup
import json

def get_cookie(response, is_dict=False):
    """Extract cookies from response object."""
    cookie_dict = requests.utils.dict_from_cookiejar(response.cookies)
    if is_dict:
        return cookie_dict
    return "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

def main():
    session = requests.Session()
    
    # Configure session-wide headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',  # Disable compression to prevent garbled text
        'Upgrade-Insecure-Requests': '1',
    })

    try:
        # Step 1: Initial request to get session cookies
        print("Fetching homepage...")
        home_response = session.get("https://www.mycourseville.com")
        home_response.raise_for_status()
        print(f"Initial Cookies: {get_cookie(home_response)}")

        # Step 2: GET login page
        login_url = "https://www.mycourseville.com/api/oauth/authorize?response_type=code&client_id=mycourseville.com&redirect_uri=https://www.mycourseville.com&login_page=itchulan"
        
        print("\nFetching login page...")
        login_page = session.get(login_url)
        login_page.raise_for_status()
        
        # Handle encoding issues
        if 'Content-Type' in login_page.headers and 'charset=' in login_page.headers['Content-Type']:
            login_page.encoding = login_page.headers['Content-Type'].split('charset=')[-1]
        else:
            login_page.encoding = 'utf-8'  # Fallback to UTF-8
            
        print(f"Login Page Cookies: {get_cookie(login_page)}")
        print(f"Response Encoding: {login_page.encoding}")

        # Step 3: Extract CSRF token
        soup = BeautifulSoup(login_page.text, 'html.parser')
        token_input = soup.find('input', {'name': '_token'})
        
        if not token_input:
            print("Error: Could not find CSRF token in login page!")
            print("Page content sample:", login_page.text[:500])
            return

        token = token_input.get('value')
        print(f"\nExtracted CSRF Token: {token}")

        # Step 4: POST login form
        login_data = {
            '_token': token,
            'username': uid,
            'password': passw,  # Replace with actual password
            'remember': 'on'
        }
        
        print("\nAttempting login...")
        login_response = session.post(
            "https://www.mycourseville.com/api/chulalogin",
            data=login_data,
            allow_redirects=True
        )
        
        # Check login success
        if login_response.status_code == 200:
            print("\nLogin successful!")
            print(f"Final Cookies: {get_cookie(login_response,True)}")
            
            # Verify by checking a protected page
            dashboard = session.get("https://www.mycourseville.com/")
            if "2024" in dashboard.text.lower():
                print("Verified - Found 2024 in dashboard")
            else:
                print("Warning: May not be properly logged in")
        else:
            print(f"\nLogin failed! Status: {login_response.status_code}")
            print("Response:", login_response.text[:500])

    except requests.exceptions.RequestException as e:
        print(f"\nError occurred: {str(e)}")

if __name__ == "__main__":
    main()