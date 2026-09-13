#!/usr/bin/env python3
import os,sys,time,termios,select
SERIAL="/dev/ttyUSB0"
fd=os.open(SERIAL,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a=termios.tcgetattr(fd); a[0]=a[1]=a[3]=0; a[2]=termios.CS8|termios.CREAD|termios.CLOCAL
cc=list(a[6]); cc[termios.VMIN]=0; cc[termios.VTIME]=0; a[6]=cc; a[4]=a[5]=termios.B115200
termios.tcsetattr(fd,termios.TCSANOW,a)
def wr(s):
    s=s.encode() if isinstance(s,str) else s
    while s: n=os.write(fd,s); s=s[n:]; time.sleep(0.01)
# drain
t=time.time()+0.3
while time.time()<t:
    try: os.read(fd,4096)
    except: pass
    time.sleep(0.05)
cmd=sys.argv[1] if len(sys.argv)>1 else "echo HELLO_$(id -u)"
wait=float(sys.argv[2]) if len(sys.argv)>2 else 4
wr("\n"+cmd+"\n")
dl=time.time()+wait; buf=b""
while time.time()<dl:
    r,_,_=select.select([fd],[],[],0.3)
    if r:
        c=os.read(fd,4096)
        if c: buf+=c
sys.stdout.write(buf.decode(errors="replace"))
