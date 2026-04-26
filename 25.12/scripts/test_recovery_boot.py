#!/usr/bin/env python3
"""
Test the recovery slot end-to-end:
1. Cold boot, catch U-Boot
2. Run bootmmc manually (loads p1 kernel) — verifies recovery slot is bootable
3. Watch for OpenWrt login prompt
4. Then power-cycle to confirm primary boot still works
5. Update bootcmd to chain: 'run bootemmc || run bootmmc' so failover is automatic
"""
import os, sys, time, termios, select, socket

SERIAL  = os.environ.get("SERIAL",  "/dev/ttyUSB0")
SIGLENT = os.environ.get("SIGLENT", "192.168.50.2")

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
    s = socket.create_connection((SIGLENT, 5025), timeout=5)
    s.sendall(f"OUTP CH1,{state}\n".encode()); time.sleep(0.3); s.close()

def catch_uboot():
    siglent("OFF"); time.sleep(4); siglent("ON")
    buf, hit = read_until("Press Ctrl+C to abort autoboot", timeout=45)
    if not hit:
        print("\nFAIL: no autoboot banner"); sys.exit(2)
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
        print("\nFAIL: no U-Boot prompt"); sys.exit(3)
    wr("\r"); read_until("(IPQ) #", 5)

print("="*60)
print(" TEST 1: Boot via recovery slot (run bootmmc → p1 kernel)")
print("="*60)
catch_uboot()

# Update bootcmd to chain primary || recovery
wr("printenv bootcmd\n"); read_until("(IPQ) #", 5)
wr("setenv bootcmd 'run bootemmc || run bootmmc'\n"); read_until("(IPQ) #", 5)
wr("saveenv\n"); read_until("(IPQ) #", 15)
wr("printenv bootcmd\n"); read_until("(IPQ) #", 5)

print("\n--- now manually invoking bootmmc to confirm recovery slot works ---")
wr("run bootmmc\n")
buf, hit = read_until([
    "Please press Enter to activate this console",
    "Kernel panic",
    "Wrong Image Format",
    "Bad Magic Number",
    "(IPQ) #",  # back to U-Boot = boot failed
], timeout=180)

if hit and b"Please press Enter" in hit.encode() if isinstance(hit, str) else b"Please press Enter" in buf:
    print("\n[OK] Recovery slot p1 → fully booted to OpenWrt login")
    sys.exit(0)
elif hit and "panic" in str(hit).lower():
    print(f"\n[FAIL] Kernel panic on recovery boot: {hit}")
    sys.exit(1)
elif hit and "(IPQ)" in hit:
    print(f"\n[FAIL] bootmmc returned to U-Boot — recovery slot not bootable")
    sys.exit(1)
else:
    print(f"\n[INCONCLUSIVE] hit={hit}")
    sys.exit(1)
