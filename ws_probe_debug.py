import socket,ssl,base64,os,struct,time
H="centrifugo.bitpin.ir"
s=socket.create_connection((H,443),10)
c=ssl.create_default_context().wrap_socket(s,server_hostname=H)
k=base64.b64encode(os.urandom(16)).decode()
req="GET /connection/websocket HTTP/1.1\r\nHost: "+H+"\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: "+k+"\r\nSec-WebSocket-Version: 13\r\n\r\n"
c.sendall(req.encode())
c.recv(4096)
def send(op,p=b""):
 m=os.urandom(4);n=len(p)
 if n<126:h=bytes([128|op,128|n])
 elif n<65536:h=bytes([128|op,128|126])+struct.pack("!H",n)
 else:h=bytes([128|op,128|127])+struct.pack("!Q",n)
 c.sendall(h+m+bytes(p[i]^m[i%4] for i in range(n)))
def recv():
 h=c.recv(2)
 if len(h)<2:return 8,b""
 op=h[0]&15;n=h[1]&127
 if n==126:n=struct.unpack("!H",c.recv(2))[0]
 elif n==127:n=struct.unpack("!Q",c.recv(8))[0]
 d=b""
 while len(d)<n:
  x=c.recv(n-len(d))
  if not x:break
  d+=x
 return op,d
send(1,b'{"connect":{},"id":1}')
op,d=recv();print("FRAME=",op,"LEN=",len(d),d[:500])
print("CONNECT=",d.decode(errors="replace"))
send(1,b'{"subscribe":{"channel":"matches:BTC_IRT"},"id":2}')
c.settimeout(5);t=time.time()
while time.time()-t<35:
 op,d=recv()
 if op==9:
  send(10,d);print("PONG_SENT");continue
 if op==8:
  print("CLOSE=",d);break
 if op==1:
  x=d.decode(errors="replace")
  print("TEXT_LEN=",len(x))
  if "matches:BTC_IRT" in x:
   print("MATCHES_OK");print(x[:300])
c.close()
