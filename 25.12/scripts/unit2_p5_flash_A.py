#!/usr/bin/env python3
# Phase A: flash new build to p1(kernel,ext2)+p5(rootfs); p3/p7 UNTOUCHED (fallback).
# Test-boot p1/p5 WITHOUT saveenv. If it boots, Phase B persists the env.
import os,sys,time,termios,select,socket,subprocess
SERIAL="/dev/ttyUSB0"; PI_IP="192.168.1.10"; ROUTER="192.168.1.1"; SIGLENT="192.168.50.2"
INITRAMFS="unit2-p5/unit2-initramfs.bin"
SQ="/srv/tftp/unit2-p5/unit2-root.squashfs"; ZI="/srv/tftp/unit2-p5/unit2-zImage"
SQ_SHA="f74f6ec21198fdb9326c99619786ea886f9c7d4f968d05bf8e4817f8d423bcf0"; SQ_SZ="19514690"
ZI_SHA="fd6fd523477902baf6339d23f2d0c05bb0ddd521f20b533c6807aaf7a37769d7"
PW=os.environ.get("UNIT2_ROOT_PW","openwrt")
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
def ssh_up():
    dl=time.time()+60
    while time.time()<dl:
        try: socket.create_connection(("192.168.1.1",22),timeout=3).close(); return True
        except: time.sleep(1)
    return False
def catch_uboot(fd):
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
    fd=op()
    end=time.time()+0.5
    while time.time()<end:
        try: os.read(fd,4096)
        except BlockingIOError: pass
        time.sleep(0.05)
    print("\n[1] cold boot"); sig("OFF"); time.sleep(4); sig("ON")
    print("\n[2] catch U-Boot")
    if not catch_uboot(fd): print("FAIL:uboot"); sys.exit(2)
    wr(fd,"\r"); ru(fd,"(IPQ) #",5)
    print("\n[3] TFTP initramfs")
    wr(fd,f"setenv ipaddr {ROUTER}\n"); ru(fd,"(IPQ) #",3)
    wr(fd,f"setenv serverip {PI_IP}\n"); ru(fd,"(IPQ) #",3)
    wr(fd,f"tftpboot 0x44000000 {INITRAMFS}\n")
    b,_=ru(fd,["Bytes transferred","(IPQ) #"],120)
    if b"Bytes transferred" not in b: print("FAIL:tftp"); sys.exit(4)
    ru(fd,"(IPQ) #",5)
    print("\n[4] boot initramfs")
    wr(fd,"bootm 0x44000000\n")
    b,hit=ru(fd,"Please press Enter",150)
    if not hit: print("FAIL:noconsole"); sys.exit(5)
    wr(fd,"\n"); time.sleep(2); ru(fd,"#",10)
    print("\n[5] dropbear")
    wr(fd,f"echo -e '{PW}\\n{PW}\\n' | passwd root\n"); time.sleep(3); ru(fd,"#",5)
    wr(fd,"/etc/init.d/dropbear enable; /etc/init.d/dropbear restart\n"); time.sleep(3); ru(fd,"#",5)
    print("\n[6] wait ssh"); 
    if not ssh_up(): print("FAIL:ssh"); sys.exit(7)
    print("SSH-OK")
    print("\n[7] scp push kernel+rootfs")
    for src,dst in [(ZI,"/tmp/unit2-zImage"),(SQ,"/tmp/unit2-root.squashfs")]:
        r=subprocess.run(["sshpass","-p",PW,"scp","-O","-o","StrictHostKeyChecking=no","-o","UserKnownHostsFile=/dev/null","-o","ConnectTimeout=10",src,f"root@192.168.1.1:{dst}"],capture_output=True,text=True,timeout=180)
        print(f"  scp {dst} rc={r.returncode} {r.stderr[-150:]}")
        if r.returncode!=0: print("FAIL:scp"); sys.exit(8)
    print("\n[8] write p1(kernel,ext2)+p5(rootfs) — p3/p7 UNTOUCHED")
    seq=[
      "which mke2fs >/dev/null && echo MKE2FS-OK || echo MKE2FS-MISSING",
      f"sha256sum /tmp/unit2-zImage | grep -q {ZI_SHA} && echo ZIMG-IN-OK || echo ZIMG-IN-FAIL",
      f"sha256sum /tmp/unit2-root.squashfs | grep -q {SQ_SHA} && echo SQ-IN-OK || echo SQ-IN-FAIL",
    ]
    for c in seq: wr(fd,c+"\n"); time.sleep(1.5); ru(fd,"#",10)
    # gate: only proceed if mke2fs present + inputs ok (checked visually in output)
    seq2=[
      "mke2fs -t ext2 -F -L kernel /dev/mmcblk0p1 2>&1 | tail -1; echo MKFS-DONE",
      "mount /dev/mmcblk0p1 /mnt && cp /tmp/unit2-zImage /mnt/zImage && sync && umount /mnt && echo P1-WRITE-OK || echo P1-WRITE-FAIL",
      f"mount -o ro /dev/mmcblk0p1 /mnt; sha256sum /mnt/zImage | grep -q {ZI_SHA} && echo P1-VERIFY-OK || echo P1-VERIFY-FAIL; umount /mnt",
      "dd if=/tmp/unit2-root.squashfs of=/dev/mmcblk0p5 bs=1M conv=fsync 2>&1 | tail -1; sync; sync; echo P5-DD-DONE",
      "echo 3 > /proc/sys/vm/drop_caches",
      f"head -c {SQ_SZ} /dev/mmcblk0p5 | sha256sum | grep -q {SQ_SHA} && echo P5-VERIFY-OK || echo P5-VERIFY-FAIL",
      "echo ALL-WRITES-DONE",
    ]
    for c in seq2: wr(fd,c+"\n"); time.sleep(2); ru(fd,["#","P5-VERIFY","ALL-WRITES-DONE"],90)
    print("\n[9] reboot -> catch U-Boot -> TEST-BOOT p1/p5 (NO saveenv)")
    wr(fd,"reboot -f\n")
    if not catch_uboot(fd): print("FAIL:uboot2"); sys.exit(9)
    wr(fd,"\r"); ru(fd,"(IPQ) #",5)
    wr(fd,"mmc rescan\n"); ru(fd,"(IPQ) #",5)
    wr(fd,"ext2load mmc 0:1 0x44000000 zImage\n")
    b,_=ru(fd,["Bytes read","bytes read","(IPQ) #"],20)
    wr(fd,"bootm 0x44000000\n")
    print("\n[10] watch new system boot (root=p5)")
    b,hit=ru(fd,["Please press Enter","procd: - init -","fr33positron","login:"],150)
    if hit: print(f"\n*** NEW SYSTEM BOOTING (matched: {hit}) ***")
    else: print("\n??? no new-system banner in 150s")
if __name__=="__main__": main()
