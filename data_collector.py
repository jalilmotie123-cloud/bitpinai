import requests,time

u="https://api.bitpin.org/api/v1/mth/orderbook/BTC_USDT/"

while True:
    try:
        d=requests.get(u,timeout=10).json()
        b=d["bids"][0]
        a=d["asks"][0]
        b10=sum(float(x[1]) for x in d["bids"][:10])
        a10=sum(float(x[1]) for x in d["asks"][:10])
        obi=(b10-a10)/(b10+a10)
        print("BTC","BID",b[0],"ASK",a[0],"OBI",round(obi,3))
    except Exception as e:
        print("ERROR:",e)
    time.sleep(5)