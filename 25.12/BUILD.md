# Build And Flash — 25.12 port

Builds OpenWrt 25.12.2 with kernel 6.12 against the upstream `openwrt-25.12` branch.

## Host prerequisites

Build host: Debian 13 (or WSL2 equivalent). Build as a regular user, not root. The 23.05 BUILD.md has the standard OpenWrt host-deps install — same here.

A distcc worker accelerates the kernel build a lot if you've got one set up; OpenWrt's `tools/install` will use `$DISTCC_HOSTS` if set. Not required.

## Clone and pin

```bash
cd ~
git clone https://github.com/openwrt/openwrt.git openwrt-25.12
cd openwrt-25.12
git checkout openwrt-25.12
./scripts/feeds update -a
./scripts/feeds install -a
```

## Required kernel patches (3 reverts for regulator race)

Drop the three patches in [`patches/`](./patches/) into `target/linux/ipq806x/patches-6.12/`:

```bash
cp /path/to/archive/patches/099*.patch \
   target/linux/ipq806x/patches-6.12/
```

These revert (in dependency order) commits `b8c325545714`, `401d078eaf2e`, and `a1d12410d9b1` — they reorganized the regulator OF lookup path in a way that exposes a probe-ordering race on this board. Without them, the lean (non-initramfs) kernel hits `mmci-pl18x: no support for card's volts` at boot and never mounts root. With them, primary autoboot is reliable.

The proper fix lands upstream as `304f5784e972` in kernel 7.0. Drop the three reverts when OpenWrt picks up that kernel.

## DTS

Copy in the modified board DTS:

```bash
cp /path/to/archive/target/linux/ipq806x/files-6.12/arch/arm/boot/dts/qcom/qcom-ipq8065-rt2600ac.dts \
   target/linux/ipq806x/files-6.12/arch/arm/boot/dts/qcom/
```

Differences from upstream:
- `chosen.bootargs = "rootfstype=squashfs,ext4 rootwait noinitrd root=/dev/mmcblk0p7"` — matches our partition layout
- `&sdcc1 { status = "okay"; };` — eMMC explicitly enabled (the 23.05 DTS had this disabled at one point)
- `&sdcc3` — SD slot wiring corrected (cd-gpios pin 63, ACTIVE_LOW, cd-inverted, bus-width 4)
- `wifi0` / `wifi1` nodes — no `nvmem-cells` for MAC; we use the userspace `ath10k_patch_mac` path because Synology's vendorpart layout doesn't fit a clean fixed-layout nvmem cell

## Base-files (MAC fix)

Three files in `files/etc/` need to land in `target/linux/ipq806x/base-files/etc/`:

```
board.d/02_network                  — adds synology,rt2600ac MAC case to ipq806x_setup_macs
hotplug.d/firmware/11-ath10k-caldata — patches per-radio MAC into pre-cal files
uci-defaults/05_set_synology_macs   — first-boot only: writes device-level macaddr into UCI
```

Together they pull the base MAC from `0:vendorpart` offset 0xd0, then derive +1 (wan), +2 (radio0), +3 (radio1).

## Required target config

Same as the 23.05 port plus a few additions for the overlay-on-eMMC layout:

```bash
cat > .config <<'EOF'
CONFIG_TARGET_ipq806x=y
CONFIG_TARGET_ipq806x_generic=y
CONFIG_TARGET_ipq806x_generic_DEVICE_synology_rt2600ac=y

# eMMC + filesystems
CONFIG_PACKAGE_kmod-fs-ext4=y
CONFIG_PACKAGE_kmod-mmc=y
CONFIG_PACKAGE_block-mount=y
CONFIG_PACKAGE_e2fsprogs=y

# USB storage (for /mnt/data — optional non-critical mount)
CONFIG_PACKAGE_kmod-usb-storage=y
CONFIG_PACKAGE_kmod-usb3=y
CONFIG_PACKAGE_kmod-fs-vfat=y

# WiFi
CONFIG_PACKAGE_ath10k-firmware-qca9984-ct=y
CONFIG_PACKAGE_kmod-ath10k-ct=y
CONFIG_PACKAGE_wpad-basic-mbedtls=y

# Optional but useful for live debugging
CONFIG_PACKAGE_ip-full=y
CONFIG_PACKAGE_tcpdump-mini=y
EOF

make defconfig
```

## Build

```bash
make -j$(nproc) V=s 2>&1 | tee build.log
```

Output of interest:

```
bin/targets/ipq806x/generic/openwrt-ipq806x-generic-synology_rt2600ac-squashfs-sysupgrade.bin
bin/targets/ipq806x/generic/openwrt-ipq806x-generic-synology_rt2600ac-initramfs-kernel.bin
```

The sysupgrade is a packed (kernel + rootfs) image; the initramfs-kernel is a kernel with rootfs in RAM, useful for one-shot recovery via TFTP boot.

## Extract kernel and rootfs from sysupgrade

```bash
SYSUPGRADE=bin/targets/ipq806x/generic/openwrt-ipq806x-generic-synology_rt2600ac-squashfs-sysupgrade.bin

# First 4 MiB is the legacy uImage-wrapped kernel
dd if="$SYSUPGRADE" of=/tmp/openwrt-kernel bs=1024 count=4096

# Rest is the rootfs squashfs
dd if="$SYSUPGRADE" of=/tmp/openwrt-rootfs.squashfs bs=1024 skip=4096
```

## Flash to eMMC

The path used during this port (live `dd` from a running OpenWrt with the running kernel as host):

```bash
# Boot once via initramfs, get the unit on the network
# Then from the laptop:
scp /tmp/openwrt-kernel.zImage root@router:/tmp/zImage
ssh root@router '
  mkdir -p /tmp/p3
  mount /dev/mmcblk0p3 /tmp/p3
  cp /tmp/zImage /tmp/p3/zImage
  umount /tmp/p3
'
scp /tmp/openwrt-rootfs.squashfs root@router:/tmp/rootfs.squashfs
ssh root@router '
  dd if=/tmp/rootfs.squashfs of=/dev/mmcblk0p7 bs=64k
  sync
'
# Set U-Boot env (see UBOOT.md)
# Reboot.
```

## Build fixes

The 23.05 archive's BUILD.md lists Python 3.13 / cpio host configure / root-owned-build-dir fixes. As of April 2026 on Debian 13, `openwrt-25.12` builds clean without those — they were 23.05-specific.

What did break for us during this port: nothing build-side. All friction was at flash and boot time; see TROUBLESHOOTING.md.
