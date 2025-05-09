from noticv import MCvnoti
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

engine = MCvnoti(show = True)
engine.login(***REMOVED***,***REMOVED***)
engine.driver.get("https://www.mycourseville.com/api/oauth/authorize?response_type=code&client_id=raZMrnZyw8hQAoFwjkzMV6hvoqd8bvcDD5HdfeJx&redirect_uri=https://alpha.mycourseville.com/&state=/assignments")


WebDriverWait(engine.driver, 10).until( EC.visibility_of_element_located((By.XPATH, '//a[@class="w-fit"]/div')))

# Extract course name
course_name = engine.driver.find_element(By.XPATH, '//a[@class="w-fit"]/div').text

# Extract assignment details
assignments = engine.driver.find_elements(By.XPATH, '//div[contains(@class, "flex flex-col gap-3 bg-light rounded-lg p-2 lg:px-4 lg:py-2")]')

for assignment in assignments: 
    # print(assignment)
    assignment_name = assignment.find_element(By.XPATH, './/div[contains(@class, "flex flex-col lg:gap-0.5")]/h5').text 
    due_date = assignment.find_element(By.XPATH, './div/div[3]/p').text 
    link = assignment.find_element(By.XPATH, './/a').get_attribute('href')
    print(f"Course Name: {course_name}")
    print(f"Assignment Name: {assignment_name}")
    print(f"Due Date: {due_date}")
    print(f"Link: {link}\n")





