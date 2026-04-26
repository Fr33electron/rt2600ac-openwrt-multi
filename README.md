# RT2600ac OpenWrt

Two completed ports of OpenWrt to the Synology RT2600ac (IPQ8065). They share hardware but diverge sharply on kernel, boot strategy, and storage layout — so they're tracked side-by-side in this repo rather than being merged into one moving target.

## Implementations

### [`23.05/`](./23.05/) — unit 1, OpenWrt 23.05.3 / kernel 5.15

The first working port. Boots from eMMC via Synology's stock U-Boot using `bootipq` (kernel + ramdisk + DTB at three load addresses). Persistent writes are on a USB key as extroot. Finished March 2026.

Key features:
- kernel on `mmcblk0p1`, squashfs rootfs on `mmcblk0p5`
- extroot overlay on USB `sda2` (USB is boot-critical)
- `bootipq` boot path — needs valid `zImage`, `rd.bin`, `dtb.dtb` files in p1's ext4
- ART partition was damaged on this unit; MAC + wifi calibration improvised

### [`25.12/`](./25.12/) — unit 2, OpenWrt 25.12.2 / kernel 6.12

Second-unit port that goes further: native eMMC boot with overlay on eMMC, USB demoted to optional non-critical mount. Required a 3-revert kernel patch set to dodge a regulator/probe-ordering race in kernel 6.12 that the lean (non-initramfs) build would otherwise hit. Finished April 2026.

Key features:
- kernel on `mmcblk0p3`, squashfs rootfs on `mmcblk0p7`, recovery slots on `p1`+`p5`
- overlay on `mmcblk0p6` ext4 (eMMC, not USB)
- `bootm` single-arg boot path with appended-DTB kernel — no ramdisk, no external DTB
- factory MACs from `0:vendorpart` offset 0xd0 (Synology OUI `00:11:32`)
- automatic recovery chain: `bootcmd=run bootemmc || run bootmmc`
- 3-revert patch set against `b8c325545714`, `401d078eaf2e`, `a1d12410d9b1`; drops when OpenWrt picks up kernel 7.0+

## Why two ports instead of upgrading the first?

The unit-2 port started as a "rebuild the same image" exercise but probing unit 2's stock Synology firmware turned up several DTS facts that contradict guesses we'd made for unit 1 — LED wiring, third-GMAC presence, SD card slot config — and once kernel 6.12 forced the regulator-race work, the boot strategy diverged enough that retrofitting v23.05 didn't make sense. The two ports are cleaner separate.

## Hardware

Both units are stock Synology RT2600ac:
- SoC: Qualcomm IPQ8065, dual Cortex-A15
- 512 MB RAM, ~3.5 GB eMMC, 8 MB SPI NOR
- 2x QCA9984 hw1.0 (5 GHz + 2.4 GHz)
- AR8337 switch (4 LAN + 1 WAN)
- Synology U-Boot 2012.07 on unit 2; 2016.01 on unit 1

Where the two implementations diverge on hardware findings, consult the per-port `HARDWARE.md`.

## Layout

Each implementation directory follows the same shape:

```
{ver}/
├── README.md             status + quick start for that port
├── HARDWARE.md           verified hardware facts (and corrections)
├── UBOOT.md              boot strategy, env values, recovery
├── BUILD.md              host setup, kernel patches, build steps
├── TROUBLESHOOTING.md    issues hit, with actual fixes
├── patches/              kernel patches against the OpenWrt tree
├── files/                base-files overlay (drops into target/.../base-files/)
├── target/               DTS + per-target file overrides
└── scripts/              utility / serial / test scripts
```

The 25.12 port also has a `backups/` reference (kernel + rootfs `dd` images) — not in git (large binaries), kept in the working tree at `~/rt2600ac-25.12-port/backups/`.

## License

GPL-2.0-or-later, consistent with upstream OpenWrt and the Linux kernel — most of the contents (DTS, kernel patches, base-files scripts) inherit GPLv2 from those projects, and the original work in this repo is licensed compatibly. See [LICENSE](./LICENSE).
