import socket,ssl,base64,os,struct,time,json,csv

HOST="centrifugo.bitpin.ir"
CHANNEL="matches:BTC_IRT"
FILE="matches_ws_live.csv"
TIMEOUT=30


def recv_exact(sock,n):
    data=b""
    while len(data)<n:
        chunk=sock.recv(n-len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data+=chunk
    return data


def ws_send(sock,opcode,payload=b""):
    mask=os.urandom(4)
    n=len(payload)
    if n<126:
        header=bytes([128|opcode,128|n])
    elif n<65536:
        header=bytes([128|opcode,128|126])+struct.pack("!H",n)
    else:
        header=bytes([128|opcode,128|127])+struct.pack("!Q",n)
    masked=bytes(payload[i]^mask[i%4] for i in range(n))
    sock.sendall(header+mask+masked)


def ws_recv(sock):
    h=recv_exact(sock,2)
    opcode=h[0]&15
    n=h[1]&127
    if n==126:
        n=struct.unpack("!H",recv_exact(sock,2))[0]
    elif n==127:
        n=struct.unpack("!Q",recv_exact(sock,8))[0]
    payload=recv_exact(sock,n) if n else b""
    return opcode,payload


def connect_ws():
    raw=socket.create_connection((HOST,443),10)
    sock=ssl.create_default_context().wrap_socket(raw,server_hostname=HOST)
    key=base64.b64encode(os.urandom(16)).decode()
    req="GET /connection/websocket HTTP/1.1\r\nHost: "+HOST+"\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: "+key+"\r\nSec-WebSocket-Version: 13\r\n\r\n"
    sock.sendall(req.encode())
    response=sock.recv(4096)
    if b"101 Switching Protocols" not in response:
        sock.close()
        raise ConnectionError("WebSocket handshake failed: "+repr(response[:200]))
    sock.settimeout(TIMEOUT)
    return sock

def save_matches(matches):
    exists=os.path.exists(FILE)
    with open(FILE,"a",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["id","price","base_amount","quote_amount","side","time"])
        if not exists:
            w.writeheader()
        for m in matches:
            w.writerow({
                "id":m.get("id",""),
                "price":m.get("price",""),
                "base_amount":m.get("base_amount",""),
                "quote_amount":m.get("quote_amount",""),
                "side":m.get("side",""),
                "time":m.get("time","")
            })
    return len(matches)


def load_seen():
    loaded=set()
    if not os.path.exists(FILE):
        return loaded
    try:
        with open(FILE,encoding="utf-8",newline="") as f:
            for row in csv.DictReader(f):
                mid=str(row.get("id","")).strip()
                if mid:
                    loaded.add(mid)
    except Exception as e:
        print("LOAD_SEEN_ERROR=",repr(e))
    print("LOADED_SEEN=",len(loaded))
    return loaded


def run_once():
    seen=load_seen()
    sock=connect_ws()
    print("WS_CONNECTED=1")
    send_json(sock,{"connect":{},"id":1})
    while True:
        op,data=ws_recv(sock)
        if op==1:
            text=data.decode(errors="replace")
            if text.strip()=="{}":
                ws_send(sock,1,b"{}")
                print("PONG_SENT")
                continue
            obj=json.loads(text)
            if obj.get("id")==1 and "connect" in obj:
                print("CONNECT=",text)
                send_json(sock,{"subscribe":{"channel":CHANNEL},"id":2})
                continue
            if obj.get("id")==2 and "subscribe" in obj:
                print("SUBSCRIBE=",text)
                print("COLLECTING=1")
                continue
            push=obj.get("push")
            if push:
                data_obj=push.get("pub",{}).get("data",{})
                matches=data_obj.get("matches",[])
                fresh=[]
                for m in matches:
                    mid=str(m.get("id",""))
                    if mid and mid not in seen:
                        fresh.append(m)
                        seen.add(mid)
                if fresh:
                    n=save_matches(fresh)
                    print("SAVED=",n,"TOTAL=",len(seen))
        elif op==9:
            ws_send(sock,10,b"")
        elif op==8:
            raise ConnectionError("websocket closed")


def send_json(sock,obj):
    payload=json.dumps(obj,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    ws_send(sock,1,payload)

if __name__ == "__main__":
    run_once()
