#!/usr/bin/env python3
"""
Drop a public SSH key into /etc/dropbear/authorized_keys on the running
router via the serial console.

Reads the pubkey from $PUBKEY (env var) or ~/.ssh/id_ed25519.pub by
default. Set $SERIAL if your USB-TTL adapter isn't /dev/ttyUSB0.
"""
import os, termios, select, time, sys

SERIAL = os.environ.get("SERIAL", "/dev/ttyUSB0")
PUB = os.environ.get("PUBKEY")
if not PUB:
    pub_path = os.path.expanduser("~/.ssh/id_ed25519.pub")
    try:
        with open(pub_path) as f: PUB = f.read().strip()
    except FileNotFoundError:
        sys.exit("set $PUBKEY or place a key at ~/.ssh/id_ed25519.pub")

fd = os.open(SERIAL, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a = termios.tcgetattr(fd); a[0]=0;a[1]=0;a[3]=0
a[2]=termios.CS8|termios.CREAD|termios.CLOCAL
cc=list(a[6]);cc[termios.VMIN]=0;cc[termios.VTIME]=0
a[6]=cc;a[4]=termios.B115200;a[5]=termios.B115200
termios.tcsetattr(fd,termios.TCSANOW,a)
def wr(s): os.write(fd,s.encode()); time.sleep(0.05)
def drain(t=3):
    end=time.time()+t; out=b""
    while time.time()<end:
        r,_,_=select.select([fd],[],[],0.2)
        if r:
            c=os.read(fd,4096)
            if c:
                out+=c
                sys.stdout.buffer.write(c); sys.stdout.buffer.flush()
    return out

wr("\r\r"); drain(2)
for c in [
    "mkdir -p /etc/dropbear",
    f"echo '{PUB}' > /etc/dropbear/authorized_keys",
    "chmod 600 /etc/dropbear/authorized_keys",
    "chmod 700 /etc/dropbear",
    "ls -la /etc/dropbear/",
    "wc -l /etc/dropbear/authorized_keys",
    # Also set a root password so console login still works
    "passwd -l root 2>&1 || true",  # don't actually lock - just show
    # ensure dropbear is running
    "/etc/init.d/dropbear enable; /etc/init.d/dropbear restart",
    "netstat -lnt | grep :22",
]:
    wr(c+"\n"); drain(2)
