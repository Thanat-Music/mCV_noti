from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


class MCvnoti:
    def __init__(self,show = False, path = None):
        self.driver = self.create_driver(show,path)

    def create_driver(self,show,path):
        chrome_options = Options()
        if not show:
            chrome_options.add_argument("--headless")
        # chrome_options.add_argument("--headless")
        driver_path = path
        driver = webdriver.Chrome(options=chrome_options)
        return driver

    def login(self, username, password):
        self.driver.get("https://www.mycourseville.com/api/oauth/authorize?response_type=code&client_id=mycourseville.com&redirect_uri=https://www.mycourseville.com&login_page=itchula")
        username_field = self.driver.find_element(By.NAME, "username")
        password_field = self.driver.find_element(By.NAME, "password")
        login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
        username_field.send_keys(username)
        password_field.send_keys(password)
        login_button.click()
        

    def get_crouse(self,year,semester):
        return self.driver.find_elements(By.XPATH, f'//a[@year="{year}" and @semester="{semester}"]')
        
    def close_browser(self):
        self.driver.quit()