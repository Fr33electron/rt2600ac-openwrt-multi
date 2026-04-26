#!/usr/bin/env python3
"""
Cold-boot router, catch U-Boot, replace `bootemmc` to use single-arg bootm
(kernel uses appended DTB, not external one). Save env. Reset and verify
eMMC autoboot reaches userspace.
"""
import os, sys, time, termios, select, socket
SERIAL  = os.environ.get("SERIAL",  "/dev/ttyUSB0")
SIGLENT = os.environ.get("SIGLENT", "192.168.50.2")

def open_serial():
    fd = os.open(SERIAL, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd); a[0]=0; a[1]=0; a[3]=0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    cc = list(a[6]); cc[termios.VMIN]=0; cc[termios.VTIME]=0
    a[6]=cc; a[4]=termios.B115200; a[5]=termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd

def wr(fd, s):
    if isinstance(s, str): s = s.encode()
    while s:
        n = os.write(fd, s); s = s[n:]; time.sleep(0.01)

def read_until(fd, needles, timeout=30):
    if isinstance(needles, str): needles = [needles]
    dl = time.time()+timeout; buf = b""
    while time.time() < dl:
        r,_,_ = select.select([fd], [], [], 0.3)
        if r:
            c = os.read(fd, 4096)
            if c:
                buf += c
                sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                for n in needles:
                    if n.encode() in buf: return buf, n
    return buf, None

def siglent(state):
    s = socket.create_connection((SIGLENT, 5025), timeout=5)
    s.sendall(f"OUTP CH1,{state}\n".encode()); time.sleep(0.3); s.close()

def main():
    fd = open_serial()
    end = time.time()+0.5
    while time.time() < end:
        try: os.read(fd, 4096)
        except BlockingIOError: pass
        time.sleep(0.05)

    print("[1] cold-boot via Siglent")
    siglent("OFF"); time.sleep(4); siglent("ON")
    buf,hit = read_until(fd, "Press Ctrl+C to abort autoboot", timeout=45)
    if not hit: print("FAIL banner"); sys.exit(2)
    dl = time.time()+10; seen=buf; last=0
    while time.time()<dl:
        if time.time()-last>0.05: wr(fd,"\x03"); last=time.time()
        r,_,_=select.select([fd],[],[],0.03)
        if r:
            c=os.read(fd,4096)
            if c:
                seen+=c; sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                if b"(IPQ) #" in seen[-400:]: break
    if b"(IPQ) #" not in seen[-400:]: print("FAIL prompt"); sys.exit(3)
    wr(fd,"\r"); read_until(fd,"(IPQ) #",5)

    print("[2] update bootemmc to use single-arg bootm")
    wr(fd, "setenv bootemmc 'mmc rescan; ext2load mmc 0:3 $kload zImage; bootm $kload'\n")
    read_until(fd, "(IPQ) #", 5)
    wr(fd, "saveenv\n")
    read_until(fd, "(IPQ) #", 30)

    print("[3] reset and watch eMMC autoboot")
    wr(fd, "reset\n")
    buf, hit = read_until(fd,
        ["Please press Enter to activate this console",
         "Kernel panic", "VFS: Cannot open root",
         "no support for card's volts", "Card stuck being busy"],
        timeout=120)
    print()
    if hit and "Please press Enter" in hit:
        print("[OK] eMMC boot via single-arg bootm reaches userspace")
        time.sleep(2); wr(fd, "\r\r")
        wr(fd, "uname -r; cat /proc/cmdline; mount | grep overlay; df -h /\n")
        read_until(fd, "#", 10)
        sys.exit(0)
    else:
        print(f"[FAIL] hit: {hit}")
        sys.exit(9)

if __name__ == "__main__":
    main()
