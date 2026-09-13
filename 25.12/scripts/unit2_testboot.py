#!/usr/bin/env python3
import os,sys,time,termios,select
SERIAL="/dev/ttyUSB0"
def op():
    fd=os.open(SERIAL,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
    a=termios.tcgetattr(fd); a[0]=a[1]=a[3]=0; a[2]=termios.CS8|termios.CREAD|termios.CLOCAL
    cc=list(a[6]); cc[termios.VMIN]=0; cc[termios.VTIME]=0; a[6]=cc; a[4]=a[5]=termios.B115200
    termios.tcsetattr(fd,termios.TCSANOW,a); return fd
def wr(fd,s):
    s=s.encode() if isinstance(s,str) else s
    while s: n=os.write(fd,s); s=s[n:]; time.sleep(0.01)
def ru(fd,needles,timeout=30):
    needles=[needles] if isinstance(needles,str) else needles
    dl=time.time()+timeout; buf=b""
    while time.time()<dl:
        r,_,_=select.select([fd],[],[],0.3)
        if r:
            c=os.read(fd,4096)
            if c:
                buf+=c; sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                for n in needles:
                    if n.encode() in buf: return buf,n
    return buf,None
def catch(fd):
    b,hit=ru(fd,"Press Ctrl+C to abort autoboot",60)
    if not hit: return False
    dl=time.time()+10; seen=b; last=0
    while time.time()<dl:
        if time.time()-last>0.05: wr(fd,"\x03"); last=time.time()
        r,_,_=select.select([fd],[],[],0.03)
        if r:
            c=os.read(fd,4096)
            if c:
                seen+=c; sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                if b"(IPQ) #" in seen[-400:]: return True
    return b"(IPQ) #" in seen[-400:]
def main():
    fd=op()
    t=time.time()+0.3
    while time.time()<t:
        try: os.read(fd,4096)
        except: pass
        time.sleep(0.05)
    print("[T1] reboot initramfs")
    wr(fd,"\n"); time.sleep(0.5); wr(fd,"reboot -f\n")
    print("[T2] catch U-Boot")
    if not catch(fd): print("FAIL-UBOOT"); sys.exit(2)
    wr(fd,"\r"); ru(fd,"(IPQ) #",5)
    print("[T3] boot p1/p5 (no saveenv)")
    wr(fd,"mmc rescan\n"); ru(fd,"(IPQ) #",8)
    wr(fd,"ext2load mmc 0:1 0x44000000 zImage\n"); ru(fd,["ytes read","(IPQ) #"],20)
    wr(fd,"bootm 0x44000000\n")
    print("[T4] watch new system (root=p5)")
    b,hit=ru(fd,["Please press Enter","procd: - init -","fr33positron","br-lan: link"],160)
    if hit: print(f"\nNEW-SYSTEM-UP matched={hit}")
    else: print("\nNO-BANNER")
if __name__=="__main__": main()
