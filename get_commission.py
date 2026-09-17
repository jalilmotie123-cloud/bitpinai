import os
import requests

API_KEY = os.getenv("BITPIN_API_KEY")
API_SECRET = os.getenv("BITPIN_API_SECRET")

login_url = "https://api.bitpin.org/api/v1/usr/authenticate/"

login_data = {
    "api_key": API_KEY,
    "secret_key": API_SECRET
}

r = requests.post(login_url, json=login_data, timeout=15)

print("LOGIN STATUS:", r.status_code)

if r.status_code != 200:
    print(r.text)
    raise SystemExit

access_token = r.json()["access"]

print("LOGIN OK")

commission_url = "https://api.bitpin.org/api/v1/mkt/commissions/"

headers = {
    "Authorization": f"Bearer {access_token}"
}

r = requests.get(commission_url, headers=headers, timeout=15)

print("COMMISSION STATUS:", r.status_code)

if r.status_code == 200:
    for x in r.json():
        if x.get("symbol") in [
            "BTC_USDT",
            "ETH_USDT",
            "XRP_USDT",
            "SOL_USDT",
            "BNB_USDT",
            "DOGE_USDT",
            "ADA_USDT",
            "XAUT_USDT"
        ]:
            print(
                x["symbol"],
                "| MAKER =", x["maker"],
                "| TAKER =", x["taker"]
            )
else:
    print(r.text)