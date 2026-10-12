import requests

r = requests.get(
    "http://127.0.0.1:9222/json"
)

print(r.status_code)
print(r.text)