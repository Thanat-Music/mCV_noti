from mcv_ import CVaScraper
import requests
import re

# mcv = CVaScraper()
api_url = "https://api.alpha.mycourseville.com/auth/login"
headers = {
    'Host': 'api.alpha.mycourseville.com',
    'Content-Length': '51',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json'}
print(f"headers: {headers}")
token = requests.post(api_url,headers=headers, json={"code": "jMcfZ20a9eEW2i6mayjc2byHJw2j2Fn8W9rc2w2M"})

print(f"!!!ALERT!!! Error: {token.status_code}")
print(f"!!!ALERT!!! Error: {token.text}")




