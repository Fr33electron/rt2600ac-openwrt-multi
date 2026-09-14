# U-Boot Notes — 25.12 port

U-Boot itself is the same Synology-shipped `2012.07-gc4831b0` used by the 23.05 port. What changed is the boot strategy: 23.05 used `bootipq` with separate `zImage` + `rd.bin` + `dtb.dtb` files; 25.12 uses single-arg `bootm` with the kernel's appended DTB.

## Catching the prompt

Power-cycle and send `Ctrl+C` while watching for `Press Ctrl+C to abort autoboot`. The reusable template lives at [`scripts/uboot_set_bootmmc.py`](./scripts/uboot_set_bootmmc.py) — copy and adapt the `catch_uboot()` function.

The U-Boot prompt is `(IPQ) #`.

## Verified load addresses (unchanged from the 23.05 port)

- `kload=0x44000000` — kernel
- `rload=0x46000000` — ramdisk (unused on this build)
- `dload=0x48000000` — DTB (unused on this build — see "Why single-arg `bootm`")

## Boot envs (verified current layout)

> **CORRECTION (2026-09-13):** the p3-first sequence and p7 primary root shown in earlier versions are **superseded**. Verified current layout: **p1/p5 primary, p3/p7 recovery** (recovery forces a RAM overlay, no automatic p5/p6 mounts). Boot policy = a **single MMC rescan**, then an inline guarded load of primary **p1/p5**, falling through to recovery **p3/p7** on failure. Automatic fallback was verified using a deliberately missing primary filename in RAM. Primary and recovery each separately passed unattended warm and cold boots. The authoritative environment is written to `0:appsblenv` (mtd9) via **Linux NOR writes** and kept privately; **never `saveenv`** on this board (found to leave a damaged / non-persisting env). Primary loads via single-arg `bootm` (appended DTB), `bootp1` -> `mmc 0:1`.

Failover is automatic only for failures U-Boot can detect (file unreadable, or `bootm` rejecting the image). A kernel that boots part-way then panics on rootfs mount is not U-Boot-visible, so the chain won't catch it — see TROUBLESHOOTING.md.

## Why single-arg `bootm` and not `bootipq`

`bootipq` on this U-Boot expects three things in memory simultaneously: kernel at `$kload`, ramdisk at `$rload`, and an external DTB at `$dload`. We tried that path early and the kernel panicked because the kernel image already has an **appended DTB** at the end of `zImage`. The external DTB at 0x48000000 then conflicted — kernel got two DTBs and chose wrong.

Single-arg `bootm $kload` tells U-Boot "the kernel image at $kload knows where its own DTB is; don't supply one." That works cleanly with appended-DTB kernels. No `rd.bin` needed — we don't have an initramfs in this build (`noinitrd` is set in the DTS chosen.bootargs).

## Kernel partition contents

Both `mmcblk0p1` and `mmcblk0p3` are ext2 filesystems containing `zImage` (and historically `rd.bin` + `dtb.dtb` from Synology, which we leave there as harmless filler). U-Boot's `ext2load mmc 0:N $kload zImage` reads the file by name from the filesystem — the U-Boot `mmc` partition number after `0:` corresponds to the Linux partition number (so `0:3` = `mmcblk0p3`).

We could have done `mmc read` to load a raw image from the partition's start, but keeping the ext2 wrapper means future updates can `cp` a new zImage in (via Linux mount) without needing exact byte alignment.

## bootargs

The **primary** kernel's `chosen.bootargs` (baked into the DTS) is:

```text
rootfstype=squashfs,ext4 rootwait noinitrd root=/dev/mmcblk0p5
```

**CORRECTION (2026-09-13):** primary root is **p5** (earlier versions said p7). The **recovery** slot (p3 kernel) is a separate build whose appended DTB sets `root=/dev/mmcblk0p7` and forces a **RAM overlay** with no automatic p5/p6 mounts. The setup therefore now has both kernel-slot **and** rootfs redundancy: p1/p5 primary + p3/p7 recovery.

## MAC warning at U-Boot

Each cold boot prints something like:

```text
Warning: eth0 MAC addresses don't match:
Address in SROM is         00:03:7f:XX:XX:01
Address in environment is  00:11:32:XX:XX:01
```

This is from the legacy U-Boot env `ethaddr` / `eth1addr` being placeholder values that don't match the SROM-stored Atheros OUI MACs. It doesn't matter for OpenWrt — we set the user-visible MACs from `0:vendorpart` in userspace (see HARDWARE.md). The warning is cosmetic and left untouched. (Do **not** `saveenv` on this board — see the boot-env correction above.)

## Saving env

**CORRECTION (2026-09-13): `saveenv` is unreliable on this board's 2012.07 U-Boot and was found to leave a damaged / non-persisting environment. Repair `0:appsblenv` (mtd9) via Linux NOR writes and re-read to verify; do not use `saveenv` for boot persistence.**

`0:appsblenv` is a 256 KiB partition in **SPI NOR** at offset ~0x2a0000–0x2e0000. Repair it via Linux NOR writes to `mtd9`, not `saveenv` (see the correction above).
