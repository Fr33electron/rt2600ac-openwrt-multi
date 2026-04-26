# Build And Flash

## Host prerequisites

Build host used:
- Debian 13
- non-root user: `<your-user>`
- clean Linux `PATH`: `/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin`

Install dependencies using Debian's OpenWrt build prerequisites. Build as the regular user, not root.

## Clone and pin version

```bash
cd ~
git clone https://github.com/openwrt/openwrt.git
cd openwrt
git checkout v23.05.3
./scripts/feeds update -a
./scripts/feeds install -a
```

## Required config

The custom target is `synology_rt2600ac` under `ipq806x/generic`.

Minimum target config:

```bash
cat > .config <<'EOF'
CONFIG_TARGET_ipq806x=y
CONFIG_TARGET_ipq806x_generic=y
CONFIG_TARGET_ipq806x_generic_DEVICE_synology_rt2600ac=y
CONFIG_PACKAGE_kmod-fs-ext4=y
CONFIG_PACKAGE_kmod-lib-crc16=y
CONFIG_PACKAGE_kmod-lib-crc32c=y
CONFIG_PACKAGE_block-mount=y
CONFIG_PACKAGE_kmod-scsi-core=y
EOF

make defconfig
```

## Build fixes required on Debian 13

### Ninja Python 3.13

`tools/ninja` needs `pipes.quote()` replaced with `shlex.quote()`.

Patch included here:
- [`build/patches/110-python-3.13-compat.patch`](./build/patches/110-python-3.13-compat.patch)

### CPIO host configure fix

The original session also needed a host-side cpio fix. The exact upstream patch file was not preserved in-tree, so this archive includes a reconstructed note patch capturing that intervention:
- [`build/patches/cpio-host-configure-fix.patch`](./build/patches/cpio-host-configure-fix.patch)

### Ownership fix

If root-owned artifacts block incremental rebuilds:

```bash
sudo chown -R "$USER:$USER" ~/openwrt/build_dir/
```

## Build commands

```bash
cd ~/openwrt
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin
make -j"$(nproc)" V=s 2>&1 | tee build.log
```

If only target images need refreshing:

```bash
cd ~/openwrt
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin
make target/linux/install -j"$(nproc)" V=s
```

## Known-good output images

Files:
- `openwrt-ipq806x-generic-synology_rt2600ac-initramfs-kernel.bin`
- `openwrt-ipq806x-generic-synology_rt2600ac-squashfs-sysupgrade.bin`

Known-good sizes:
- initramfs kernel: about `6.7M`
- sysupgrade: about `7.9M`

Known-good SHA256:
- `56f2ff92f257553e3ffb9496901700bdbc127021c4c0e20da7dbcd5a912325ee`  initramfs
- `57849f0a3dd24137818de546e5caaa3a4e936e985dff1a92d0d0c48d82e5dbd3`  sysupgrade

## Extract split kernel and rootfs

```bash
SYSUPGRADE=~/openwrt/bin/targets/ipq806x/generic/openwrt-ipq806x-generic-synology_rt2600ac-squashfs-sysupgrade.bin

dd if="$SYSUPGRADE" of=/tmp/openwrt-kernel bs=1024 count=4096
dd if="$SYSUPGRADE" of=/tmp/openwrt-rootfs.squashfs bs=1024 skip=4096
```

`openwrt-kernel` is a U-Boot legacy `uImage`. `openwrt-rootfs.squashfs` is the rootfs for `mmcblk0p5`.

## Build boot.img

`mmcblk0p1` must contain an ext4 filesystem with named files `zImage`, `rd.bin`, and `dtb.dtb`.

```bash
INITRAMFS=~/openwrt/bin/targets/ipq806x/generic/openwrt-ipq806x-generic-synology_rt2600ac-initramfs-kernel.bin
DTB=~/openwrt/build_dir/target-arm_cortex-a15+neon-vfpv4_musl_eabi/linux-ipq806x_generic/image-qcom-ipq8065-rt2600ac.dtb

dd if=/dev/zero of=/tmp/boot.img bs=1M count=16
~/openwrt/staging_dir/host/bin/mkfs.ext4 -L boot -O ^metadata_csum,^64bit -b 4096 /tmp/boot.img
mkdir -p /tmp/bootmnt
mount -o loop /tmp/boot.img /tmp/bootmnt
cp /tmp/openwrt-kernel /tmp/bootmnt/zImage
cp /tmp/empty-rd.bin /tmp/bootmnt/rd.bin
cp "$DTB" /tmp/bootmnt/dtb.dtb
sync
umount /tmp/bootmnt
```

The `rd.bin` file is an empty but valid ramdisk `uImage`, required because `bootipq` rejects missing or invalid ramdisk formats.

