# U-Boot Notes — 25.12 port

U-Boot itself is the same Synology-shipped `2012.07-gc4831b0` used by the 23.05 port. What changed is the boot strategy: 23.05 used `bootipq` with separate `zImage` + `rd.bin` + `dtb.dtb` files; 25.12 uses single-arg `bootm` with the kernel's appended DTB.

## Catching the prompt

Power-cycle and send `Ctrl+C` while watching for `Press Ctrl+C to abort autoboot`. The reusable template lives at [`scripts/uboot_set_bootmmc.py`](./scripts/uboot_set_bootmmc.py) — copy and adapt the `catch_uboot()` function.

The U-Boot prompt is `(IPQ) #`.

## Verified load addresses (unchanged from the 23.05 port)

- `kload=0x44000000` — kernel
- `rload=0x46000000` — ramdisk (unused on this build)
- `dload=0x48000000` — DTB (unused on this build — see "Why single-arg `bootm`")

## Boot envs (final saved values)

```text
bootcmd=run bootemmc || run bootmmc
bootemmc=mmc rescan; ext2load mmc 0:3 $kload zImage; bootm $kload
bootmmc=mmc rescan; ext2load mmc 0:1 $kload zImage; bootm $kload
```

The chain in `bootcmd` makes failover automatic: if `bootemmc` fails (file unreadable or `bootm` rejects the image), U-Boot falls through to `bootmmc` and tries the recovery slot. **Caveat**: this only works for failures U-Boot can detect — a kernel that boots part-way and then panics on rootfs mount is not a U-Boot-visible failure, so the chain won't catch it. See TROUBLESHOOTING.md.

## Why single-arg `bootm` and not `bootipq`

`bootipq` on this U-Boot expects three things in memory simultaneously: kernel at `$kload`, ramdisk at `$rload`, and an external DTB at `$dload`. We tried that path early and the kernel panicked because the kernel image already has an **appended DTB** at the end of `zImage`. The external DTB at 0x48000000 then conflicted — kernel got two DTBs and chose wrong.

Single-arg `bootm $kload` tells U-Boot "the kernel image at $kload knows where its own DTB is; don't supply one." That works cleanly with appended-DTB kernels. No `rd.bin` needed — we don't have an initramfs in this build (`noinitrd` is set in the DTS chosen.bootargs).

## Kernel partition contents

Both `mmcblk0p1` and `mmcblk0p3` are ext2 filesystems containing `zImage` (and historically `rd.bin` + `dtb.dtb` from Synology, which we leave there as harmless filler). U-Boot's `ext2load mmc 0:N $kload zImage` reads the file by name from the filesystem — the U-Boot `mmc` partition number after `0:` corresponds to the Linux partition number (so `0:3` = `mmcblk0p3`).

We could have done `mmc read` to load a raw image from the partition's start, but keeping the ext2 wrapper means future updates can `cp` a new zImage in (via Linux mount) without needing exact byte alignment.

## bootargs

The kernel's `chosen.bootargs` is baked into the DTS:

```text
rootfstype=squashfs,ext4 rootwait noinitrd root=/dev/mmcblk0p7
```

This is what wins for primary boot. For a real recovery slot that mounts `mmcblk0p5` as root, the DTS would need to be either rebuilt with `root=mmcblk0p5`, or modified to leave `chosen.bootargs` empty so U-Boot's env can override. We didn't do that yet — the current `bootmmc` recovery boots the **same kernel** which mounts the **same p7 rootfs**, giving us kernel-slot redundancy but not rootfs redundancy. Worth revisiting if you want true rootfs failover.

## MAC warning at U-Boot

Each cold boot prints something like:

```text
Warning: eth0 MAC addresses don't match:
Address in SROM is         00:03:7f:XX:XX:01
Address in environment is  00:11:32:XX:XX:01
```

This is from the legacy U-Boot env `ethaddr` / `eth1addr` being placeholder values that don't match the SROM-stored Atheros OUI MACs. It doesn't matter for OpenWrt — we set the user-visible MACs from `0:vendorpart` in userspace (see HARDWARE.md). The warning is cosmetic. Could be silenced by `setenv ethaddr <SROM-value>` and `saveenv`, but we left it untouched.

## Saving env

`saveenv` writes to `0:appsblenv` (NAND offset ~0x2a0000–0x2e0000, 256 KiB). Erase + write takes about a second. Visible in the U-Boot output as repeated `Erasing at 0x2aXXXX` lines.
