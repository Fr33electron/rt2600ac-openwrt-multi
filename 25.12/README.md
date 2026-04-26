# RT2600ac OpenWrt 25.12.2

This archive captures a working OpenWrt 25.12.2 port to the Synology RT2600ac, completed in April 2026. It supersedes the parallel `../23.05/` archive for the parts that differ — the 23.05 archive is still the reference for things common to both kernel branches.

## Current status

- OpenWrt 25.12.2 (kernel 6.12.74) boots from eMMC every reboot
- kernel lives on `mmcblk0p3`, recovery mirror on `mmcblk0p1`
- squashfs rootfs on `mmcblk0p7`, recovery mirror on `mmcblk0p5`
- overlay (writable layer) on `mmcblk0p6`, ext4, ~2 GB
- USB stick at `/mnt/data` for non-critical data (not part of boot requirements)
- both QCA9984 radios serve APs
- WAN can be either the eth `wan` port (DHCP) or a wifi-STA uplink to a 2.4 GHz upstream AP on `phy1-sta0` — both wired up; STA was used during bench bring-up
- LAN defaults to `192.168.1.1/24` in the shipped UCI; change in `/etc/config/network` as desired
- factory MACs from `0:vendorpart` (Synology OUI `00:11:32`) — see HARDWARE.md

## Differences from the 23.05 port

| | 23.05.3 | 25.12.2 |
|---|---|---|
| OpenWrt | 23.05.3 | 25.12.2 |
| Kernel | 5.15.150 | 6.12.74 |
| Kernel patches | none specific | 3 reverts for regulator race |
| Boot command | `bootipq` (zImage + rd.bin + dtb.dtb) | `bootm` single-arg (appended DTB) |
| Kernel partition | `mmcblk0p1` | `mmcblk0p3` (p1 is now recovery mirror) |
| Rootfs partition | `mmcblk0p5` | `mmcblk0p7` (p5 is now recovery mirror) |
| Overlay | extroot on USB `sda2` | `mmcblk0p6` ext4 on eMMC |
| USB role | extroot (boot-critical) | `/mnt/data` (optional) |
| MAC source | improvised — ART damaged | `0:vendorpart` offset 0xd0 |
| Recovery slot | none | p1 kernel + p5 rootfs (kernel-slot redundancy; see UBOOT.md) |

## Quick start for a fresh unit

1. Build the image from [BUILD.md](./BUILD.md) (requires the 3 kernel reverts, modified DTS, and base-files MAC scripts in this archive).
2. Catch U-Boot via serial (any USB-TTL adapter on the 6-pin header — see HARDWARE.md for pinout). `scripts/uboot_set_bootmmc.py` is a template that drives serial + a Siglent SPD3303X bench supply.
3. Boot the initramfs/sysupgrade once over TFTP or USB.
4. `dd` kernel to `/dev/mmcblk0p3`, rootfs to `/dev/mmcblk0p7`.
5. Save the U-Boot env: `bootcmd=run bootemmc || run bootmmc`, `bootemmc=mmc rescan; ext2load mmc 0:3 $kload zImage; bootm $kload`, same with `0:1` for `bootmmc`. (Note: the chain `||` doesn't auto-fall-back as written; see TROUBLESHOOTING.md for the actual workaround.)
6. Cold boot. The first-boot uci-defaults script reads vendorpart and writes the right MACs into UCI.
7. Configure WAN (eth or STA), wifi APs, DHCP. UCI changes go to overlay automatically.

## Known caveats

- **eMMC regulator race not fully eliminated.** The 3 kernel reverts make primary autoboot reliable (5/5 cold boots in stress test), but invoking `run bootmmc` manually after sitting at the U-Boot prompt has triggered the original `mmci-pl18x: no support for card's volts` error at least once. See TROUBLESHOOTING.md. Real upstream fix is in kernel 7.0+; we'll drop the reverts when OpenWrt picks up that kernel.
- **eth0/eth1 (DSA CPU ports) still show random LAA MACs.** They aren't user-visible (peers see the bridge / wan port MAC) so it's cosmetic.
- **Boot to fully-online takes ~165 s.** SSH up at ~100 s, ath10k firmware ready around +60 s, wpa_supplicant association and DHCP another ~10 s. The big chunk is ath10k firmware init (50 s of ~14 → 60 s gap in dmesg) — characteristic of QCA9984 + CT firmware on this platform, not unique to this port.

## Layout of this archive

- [`patches/`](./patches/) — three OpenWrt patches against `target/linux/ipq806x/patches-6.12/`
- [`target/linux/ipq806x/files-6.12/.../qcom-ipq8065-rt2600ac.dts`](./target/linux/ipq806x/files-6.12/arch/arm/boot/dts/qcom/qcom-ipq8065-rt2600ac.dts) — modified DTS
- [`files/etc/`](./files/) — base-files overlay (MAC fix triad + fstab default)
- [`scripts/`](./scripts/) — U-Boot, serial, stress, recovery test scripts
- backup of running p3 + p7 (`dd` images) lives outside the repo — rebuild from source per BUILD.md
