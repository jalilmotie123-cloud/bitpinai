import socket,ssl,base64,os,json,struct,time
h="centrifugo.bitpin.ir"
s=socket.create_connection((h,443),10)
c=ssl.create_default_context().wrap_socket(s,server_hostname=h)
k=base64.b64encode(os.urandom(16)).decode()
q="GET /connection/websocket HTTP/1.1\r\nHost: "+h+"\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: "+k+"\r\nSec-WebSocket-Version: 13\r\n\r\n"
c.sendall(q.encode()); c.recv(4096)
def send(p):
 m=os.urandom(4); c.sendall(bytes([129,len(p)|128])+m+bytes(p[i]^m[i%4] for i in range(len(p))))
send(b"{\"connect\":{},\"id\":1}"); print("CONNECT=",c.recv(65535).decode("utf-8","replace"))
send(b"{\"subscribe\":{\"channel\":\"matches:BTC_IRT\"},\"id\":2}"); print("SUB=",c.recv(65535).decode("utf-8","replace"))
c.settimeout(65); end=time.time()+60
while time.time()<end:
 try:
  x=c.recv(65535)
  if not x: print("CLOSED"); break
  print("FRAME_HEX=",x.hex())
  if len(x)>=2 and (x[0]&15)==9: c.sendall(bytes([138,x[1]&127])+x[2:]); print("PONG_SENT"); continue
  if len(x)>=2 and (x[0]&15)==1:
   n=x[1]&127; p=2
   if n==126: n=struct.unpack("!H",x[2:4])[0]; p=4
   elif n==127: n=struct.unpack("!Q",x[2:10])[0]; p=10
   t=x[p:p+n].decode("utf-8","replace"); print("TEXT=",t); (send(b"{}") if t=="{}" else None)
 except socket.timeout:
  print("TIMEOUT_60S"); break
c.close()
