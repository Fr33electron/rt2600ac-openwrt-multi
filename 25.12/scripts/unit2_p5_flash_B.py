#!/usr/bin/env python3
# DEPRECATED (2026-09-13): the saveenv persistence below was found UNRELIABLE on this
# board 2012.07 U-Boot (leaves a damaged / non-persisting env). Repair 0:appsblenv (mtd9)
# via Linux NOR writes and re-read to verify instead. Kept for reference only.
#
# Phase B: persist bootcmd to boot p1(kernel)/p5(rootfs), fallback to old bootemmc (p3/p7).
# VERIFY env via printenv BEFORE saveenv. mtd9 backup exists as ultimate restore.
import os,sys,time,termios,select,socket
SERIAL="/dev/ttyUSB0"; SIGLENT="192.168.50.2"
BOOTP1="mmc rescan; ext2load mmc 0:1 0x44000000 zImage; bootm 0x44000000"
BOOTCMD="run bootp1; run bootemmc"
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
def sig(state):
    s=socket.create_connection((SIGLENT,5025),timeout=5); s.sendall(f"OUTP CH1,{state}\n".encode()); time.sleep(0.3); s.close()
def catch(fd):
    b,hit=ru(fd,"Press Ctrl+C to abort autoboot",45)
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
    import sys as _sys
    _sys.stderr.write(
        "REFUSING TO RUN: unit2_p5_flash_B.py is disabled.\n"
        "The saveenv persistence below was found UNRELIABLE/DAMAGING on this board's\n"
        "2012.07 U-Boot (leaves a damaged / non-persisting env). Repair 0:appsblenv\n"
        "(mtd9) via Linux NOR writes and re-read to verify instead.\n")
    _sys.exit(2)
    # --- original (disabled, kept for reference) ---
    fd=op()
    print("\n[B1] cold boot"); sig("OFF"); time.sleep(4); sig("ON")
    if not catch(fd): print("FAIL:uboot"); sys.exit(2)
    wr(fd,"\r"); ru(fd,"(IPQ) #",5)
    print("\n[B2] setenv (single-quoted)")
    wr(fd, f"setenv bootp1 '{BOOTP1}'\n"); ru(fd,"(IPQ) #",4)
    wr(fd, f"setenv bootcmd '{BOOTCMD}'\n"); ru(fd,"(IPQ) #",4)
    print("\n[B3] VERIFY via printenv (gate before saveenv)")
    wr(fd,"printenv bootp1\n"); b1,_=ru(fd,"(IPQ) #",4)
    wr(fd,"printenv bootcmd\n"); b2,_=ru(fd,"(IPQ) #",4)
    txt=(b1+b2).decode(errors="replace")
    ok = ("ext2load mmc 0:1" in txt) and ("run bootp1" in txt)
    if not ok:
        print("\n*** ENV VERIFY FAILED — NOT saving. Old bootcmd intact (auto-recovers). ***")
        wr(fd,"reset\n"); time.sleep(1); sys.exit(3)
    print("\n[B4] env verified -> saveenv")
    wr(fd,"saveenv\n"); ru(fd,["done","Writing","(IPQ) #"],10); ru(fd,"(IPQ) #",6)
    print("\n[B5] boot via persisted bootcmd")
    wr(fd,"boot\n")
    b,hit=ru(fd,["Please press Enter","procd: - init -","fr33positron","login:"],150)
    if hit: print(f"\n*** PERSISTED BOOT OK (matched {hit}) ***")
    else: print("\n??? no banner after persisted boot")
if __name__=="__main__": main()
