import httpx

url = "https://www.naukri.com/jobapi/v3/search"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "appid": "109",
    "systemid": "109"
}
params = {
    "noOfResults": 20,
    "keyword": "python",
    "location": "india"
}

r = httpx.get(url, params=params, headers=headers)
print("Status:", r.status_code)
try:
    print(r.json())
except:
    print("Raw text:", r.text[:500])
