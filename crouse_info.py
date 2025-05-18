from noticv import MCvnoti
from selenium.webdriver.common.by import By
import time

engine = MCvnoti(show = True)
engine.login('uid','passw')
engine.driver.get("https://www.mycourseville.com/api/oauth/authorize?response_type=code&client_id=raZMrnZyw8hQAoFwjkzMV6hvoqd8bvcDD5HdfeJx&redirect_uri=https://alpha.mycourseville.com/&state=/course")


time.sleep(3)
### get all course 
a_tags = engine.driver.find_elements(By.CSS_SELECTOR, 'a.w-full')
for a_tag in a_tags:
    # Extract the href attribute
    href = a_tag.get_attribute('href')
    
    text = a_tag.text
    text = a_tag.text.strip().split('\n') 
    course_code = text[0].strip() if len(text) > 0 else "No course ID found" 
    course_title = text[1].strip() if len(text) > 1 else "No course title found" 
    semester = text[2].strip() if len(text) > 2 else "No course semester found" 

    try:
        img_src = a_tag.find_element(By.TAG_NAME, 'img').get_attribute('src') 
    except:
        img_src = "No image found"

    # Print the extracted data
    print(f'Link: {href}')
    print(f'Text: {text}')
    print(f'Image Source: {img_src}')
    print(f'Course Code: {course_code}')
    print(f'Course Title: {course_title}')
    print(f'Semester: {semester}')
    print('---')


