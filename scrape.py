from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Configure Chrome options
chrome_options = Options()
# chrome_options.add_argument("--auto-open-devtools-for-tabs")  # Open DevTools automatically
# chrome_options.add_argument("--headless")  # Run in headless mode for automation without UI

# Create a WebDriver instance
driver_path = 'path/to/chromedriver'  # Update with the path to your chromedriver
service = Service()
driver = webdriver.Chrome(service=service, options=chrome_options)
# driver.execute_cdp_cmd('Network.enable', {})

def capture_network_traffic(driver):
    logs = driver.execute_cdp_cmd('Network.getAllCookies', {})
    return logs
print("Cookies before:", driver.get_cookies())
# Navigate to the login page
driver.get("https://www.mycourseville.com")
page_source = driver.page_source 
print("Cookies after:", driver.get_cookies())

# # Locate the username, password fields and login button
# # username_field = WebDriverWait(driver, 10).until( EC.presence_of_element_located((By.NAME, "username")))
# username_field = driver.find_element(By.NAME, "username")
# password_field = driver.find_element(By.NAME, "password")
# login_button = driver.find_element(By.XPATH, "//button[@type='submit']")

# # Fill in the login details
# username_field.send_keys(***REMOVED***)
# password_field.send_keys(***REMOVED***)

# # Click the login button
# login_button.click()

# # network_logs = capture_network_traffic(driver)
# # print(network_logs)

# # Verify if login was successful by checking for a specific element on the dashboard
# # time.sleep(5)
# print("Logged in successfully!")
# a = driver.find_elements(By.XPATH, '//*[@year="2024"]')
# print([i.text for i in a])

# Close the browser
driver.quit()
