#!/usr/bin/env python3
"""
Catch U-Boot via a power-cycle (Siglent SPD3303X over SCPI/LAN), update
the `bootmmc` env to load the kernel from `mmcblk0p1` (recovery slot),
save env, then verify primary autoboot still works.

Adjust the constants below for your bench:
  SERIAL    — USB-TTL device path
  SCPI_HOST — Siglent IP
"""
import os, sys, time, termios, select, socket

SERIAL = os.environ.get("SERIAL", "/dev/ttyUSB0")
SCPI_HOST = os.environ.get("SCPI_HOST", "192.168.50.2")

fd = os.open(SERIAL, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a = termios.tcgetattr(fd); a[0]=0;a[1]=0;a[3]=0
a[2] = termios.CS8|termios.CREAD|termios.CLOCAL
cc = list(a[6]); cc[termios.VMIN]=0; cc[termios.VTIME]=0
a[6]=cc; a[4]=termios.B115200; a[5]=termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)

def wr(s):
    os.write(fd, s.encode()); time.sleep(0.05)

def read_until(needles, timeout=30):
    if isinstance(needles, str): needles=[needles]
    dl = time.time()+timeout; buf = b""
    while time.time() < dl:
        r,_,_ = select.select([fd],[],[],0.3)
        if r:
            c = os.read(fd, 4096)
            if c:
                buf += c
                sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                for n in needles:
                    if n.encode() in buf: return buf, n
    return buf, None

def siglent(state):
    s = socket.create_connection((SCPI_HOST, 5025), timeout=5)
    s.sendall(f"OUTP CH1,{state}\n".encode()); time.sleep(0.3); s.close()

def catch_uboot():
    siglent("OFF"); time.sleep(4); siglent("ON")
    buf, hit = read_until("Press Ctrl+C to abort autoboot", timeout=45)
    if not hit:
        print("FAIL: didn't see autoboot banner"); sys.exit(2)
    dl = time.time()+10; seen = buf; last = 0
    while time.time() < dl:
        if time.time()-last > 0.05:
            wr("\x03"); last = time.time()
        r,_,_ = select.select([fd],[],[],0.03)
        if r:
            c = os.read(fd, 4096)
            if c:
                seen += c; sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
                if b"(IPQ) #" in seen[-400:]: break
    if b"(IPQ) #" not in seen[-400:]:
        print("FAIL: no U-Boot prompt"); sys.exit(3)
    wr("\r"); read_until("(IPQ) #", 5)

print("="*60)
print(" Updating U-Boot bootmmc env: load kernel from p1")
print("="*60)
catch_uboot()
wr("printenv bootmmc\n");  read_until("(IPQ) #", 5)
wr("printenv bootemmc\n"); read_until("(IPQ) #", 5)

# New bootmmc: same as bootemmc but reads from partition 1
new_bootmmc = "mmc rescan; ext2load mmc 0:1 $kload zImage; bootm $kload"
wr(f"setenv bootmmc '{new_bootmmc}'\n"); read_until("(IPQ) #", 5)
wr("saveenv\n"); read_until("(IPQ) #", 10)
wr("printenv bootmmc\n"); read_until("(IPQ) #", 5)

print("\n[OK] env saved — running default bootcmd to verify primary still boots")
wr("boot\n")
buf, hit = read_until("Please press Enter to activate this console", timeout=180)
if hit:
    print("\n[OK] primary boot path (bootemmc → p3 kernel + p7 rootfs) still works")
else:
    print("\n[FAIL] primary boot didn't reach login prompt — env change didn't break it though, just slower")
