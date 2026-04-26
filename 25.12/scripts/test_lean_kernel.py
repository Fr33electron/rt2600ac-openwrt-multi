#!/usr/bin/env python3
"""
Cold-boot router, TFTP-load a lean kernel (no initramfs), watch first ~15
seconds of dmesg for the mmci-pl18x volts race signature.

Usage: test_lean_kernel.py <kernel-tftp-path>
  e.g. test_lean_kernel.py lean-6.6.uimage
       test_lean_kernel.py lean-6.12-4rev.uimage

Verdict:
  PASS = mmcblk0 enumerates without "no support for card's volts"
  FAIL = volts error appears before card init

The kernel will eventually panic on missing rootfs (rootwait + nonexistent
root device), but mmci probe happens at ~1.5s and the volts message either
shows up immediately or doesn't. We watch for ~15s which is plenty.
"""
import os, sys, time, termios, select, socket

if len(sys.argv) != 2:
    print("usage: test_lean_kernel.py <tftp-filename>"); sys.exit(1)
KERNEL = sys.argv[1]

SERIAL  = os.environ.get("SERIAL",  "/dev/ttyUSB0")
TFTP_SERVER = os.environ.get("TFTP_SERVER", "192.168.1.10")
ROUTER  = os.environ.get("ROUTER",  "192.168.1.1")
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
    dl = time.time() + timeout
    buf = b""
    while time.time() < dl:
        r,_,_ = select.select([fd], [], [], 0.3)
        if r:
            c = os.read(fd, 4096)
            if c:
                buf += c
                sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                for n in needles:
                    if n.encode() in buf:
                        return buf, n
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

    print(f"[1] cold-boot via Siglent (testing kernel: {KERNEL})")
    siglent("OFF"); time.sleep(4); siglent("ON")

    print("[2] Ctrl+C autoboot")
    buf,hit = read_until(fd, "Press Ctrl+C to abort autoboot", timeout=45)
    if not hit: print("FAIL: no autoboot banner"); sys.exit(2)
    dl = time.time()+10; seen=buf; last=0
    while time.time()<dl:
        if time.time()-last>0.05: wr(fd,"\x03"); last=time.time()
        r,_,_=select.select([fd],[],[],0.03)
        if r:
            c=os.read(fd,4096)
            if c:
                seen+=c; sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                if b"(IPQ) #" in seen[-400:]: break
    if b"(IPQ) #" not in seen[-400:]: print("FAIL: no prompt"); sys.exit(3)
    wr(fd,"\r"); read_until(fd,"(IPQ) #",5)

    print(f"[3] tftpboot {KERNEL}")
    wr(fd,f"setenv ipaddr {ROUTER}\n");   read_until(fd,"(IPQ) #",3)
    wr(fd,f"setenv serverip {TFTP_SERVER}\n");  read_until(fd,"(IPQ) #",3)
    wr(fd,f"tftpboot 0x44000000 {KERNEL}\n")
    b,_=read_until(fd,["Bytes transferred","T T T T","(IPQ) #"],90)
    if b"Bytes transferred" not in b: print("FAIL tftp"); sys.exit(4)
    read_until(fd,"(IPQ) #",5)

    print("[4] bootm (single-arg, kernel has appended DTB)")
    wr(fd,"bootm 0x44000000\n")

    # Watch for ~15 seconds — enough for both volts (early) and card-init (early)
    print("[5] capturing 15 seconds of dmesg")
    end = time.time() + 15
    buf = b""
    while time.time() < end:
        r,_,_ = select.select([fd], [], [], 0.3)
        if r:
            c = os.read(fd, 4096)
            if c:
                buf += c
                sys.stdout.buffer.write(c); sys.stdout.buffer.flush()

    print("\n\n" + "="*60)
    if b"no support for card's volts" in buf or b"Card stuck being busy" in buf:
        print(f"FAIL — race observed in {KERNEL}")
        race = True
    elif b"new high speed MMC card" in buf or b"mmcblk0:" in buf:
        print(f"PASS — eMMC enumerated cleanly in {KERNEL}")
        race = False
    else:
        print(f"INCONCLUSIVE — neither race nor success observed for {KERNEL}")
        race = None
    print("="*60)

if __name__ == "__main__":
    main()
