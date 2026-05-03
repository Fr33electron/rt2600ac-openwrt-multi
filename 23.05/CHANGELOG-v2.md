# 23.05 v2 changes

The original v1 port (March 2026) booted from eMMC but kept the writable
overlay on a USB key (`/dev/sda2` extroot). That made USB boot-critical
and meant any USB-stack hiccup took the rootfs down with it. v2 (May
2026) addresses that and adds a few requested features:

| Area | v1 | v2 |
|---|---|---|
| Overlay | `/dev/sda2` (USB stick) | `/dev/mmcblk0p6` (eMMC ext4) |
| SD card slot (`12180000.sdcc`) | Not in DTS | Live as `mmc1`, ext4 mountable |
| USB-net drivers | Not built | `cdc_ether`, `cdc_ncm`, `ipheth`, `rndis_host`, `usbnet` baked into the squashfs |
| USB tethering (Pixel-class NCM) | Crashes the kernel on bind | Works — see kernel patch |
| `e2fsprogs` (`mkfs.ext4`, `e2fsck`, `dumpe2fs`) | Not present | Baked in |
| Web UI (LuCI) | Not installed | `luci` + `luci-ssl-openssl` + `luci-app-firewall` + `luci-app-opkg` baked in; HTTPS on :443 |

Run-time behaviour after v2 sysupgrade-style flash:
- LAN: `br-lan` over `eth1` (the GMAC connected to the AR8337 switch)
- WAN: configurable; tested with `usb0` (Pixel USB tether) as `proto=dhcp`
- Overlay: persistent ext4 on `mmcblk0p6` with UUID
  `09556310-5e0e-4879-affd-31f2ba325d56`
- USB stick is no longer required for boot; safe to unplug

## What's in this directory

- `patches/780-usbnet-defensive-null-dev-addr.patch` — the kernel patch
  that lets `usbnet_probe()` survive devices whose `alloc_etherdev()`
  returns a `net_device` with `dev_addr == NULL`. Drop it in
  `target/linux/generic/pending-5.15/` of an OpenWrt 23.05 tree before
  `make`. See `notes/cdc_ncm-pixel-crash.md` for how it was diagnosed.
- `notes/cdc_ncm-pixel-crash.md` — annotated kernel oops trace and fix
  walkthrough.

## Files modified in the build tree (23.05.3)

```
target/linux/ipq806x/files-5.15/arch/arm/boot/dts/qcom-ipq8065-rt2600ac.dts
files/etc/config/fstab
.config
target/linux/generic/pending-5.15/780-usbnet-defensive-null-dev-addr.patch  (new)
```

## DTS changes (`qcom-ipq8065-rt2600ac.dts`)

```dts
aliases {
    sdcc3 = &sdcc3;
    /*
     * Force mmc host indices so eMMC stays mmc0 (mmcblk0*) and the SD
     * slot is mmc1 (mmcblk1*).  Without these the mainline DT order
     * lets the SD slot probe first and steal mmcblk0.
     */
    mmc0 = &sdcc1;
    mmc1 = &sdcc3;
};

&qcom_pinmux {
    sdcc3_pins: sdcc3-state {
        clk  { pins = "sdc3_clk";  drive-strength = <8>; bias-disable;  };
        cmd  { pins = "sdc3_cmd";  drive-strength = <8>; bias-pull-up;  };
        data { pins = "sdc3_data"; drive-strength = <8>; bias-pull-up;  };
    };
    sdcc3_cd_pins: sdcc3-cd-state {
        mux { pins = "gpio63"; function = "gpio";
              drive-strength = <2>; bias-pull-up; };
    };
};

/*
 * SD card slot (mainline qcom-ipq8064.dtsi defines sdcc3@12180000 with
 * status="disabled"; we override the board-specific bits).  Verified
 * polarity on this hardware:
 *   card IN  → gpio63 reads LOW
 *   card OUT → gpio63 reads HIGH
 * GPIO_ACTIVE_LOW alone is correct here — do NOT add `cd-inverted`,
 * which would double-negate.
 *
 * Mainline declares only `vqmmc-supply` for sdcc3 and no `vmmc-supply`,
 * which leaves the mmci core unable to compute a valid OCR mask and
 * fails with "no support for card's volts" on insert.  Tie main power
 * to the same fixed 3.3V SDCC regulator used by the eMMC.
 */
&sdcc3 {
    status = "okay";
    bus-width = <4>;
    vmmc-supply = <&vsdcc_fixed>;
    cd-gpios = <&qcom_pinmux 63 GPIO_ACTIVE_LOW>;
    pinctrl-0 = <&sdcc3_pins &sdcc3_cd_pins>;
    pinctrl-names = "default";
};
```

## fstab change (`files/etc/config/fstab`)

```
config mount
    option target '/overlay'
    option uuid   '09556310-5e0e-4879-affd-31f2ba325d56'
    option fstype 'ext4'
    option enabled '1'
```

## .config additions

```
CONFIG_PACKAGE_kmod-usb-net=y
CONFIG_PACKAGE_kmod-usb-net-rndis=y
CONFIG_PACKAGE_kmod-usb-net-cdc-ether=y
CONFIG_PACKAGE_kmod-usb-net-cdc-ncm=y
CONFIG_PACKAGE_kmod-usb-net-ipheth=y
CONFIG_PACKAGE_e2fsprogs=y

# LuCI web UI (HTTPS via openssl)
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_luci-ssl-openssl=y
CONFIG_PACKAGE_luci-app-firewall=y
CONFIG_PACKAGE_luci-app-opkg=y

# Force openssl-based wpa supplicant so libustream-mbedtls isn't pulled in
# (would file-clash with libustream-openssl that luci-ssl-openssl needs)
CONFIG_PACKAGE_wpad-basic-openssl=y
# CONFIG_PACKAGE_wpad-basic-mbedtls is not set
```

If you've previously built with mbedtls in the image and switch to openssl
without cleaning, the install step file-clashes on `/lib/libustream-ssl.so`
because both packages provide it. Cure: delete the stale staging markers
and stale ipks before rebuilding, e.g.

```
rm -f staging_dir/target-*/pkginfo/{ustream-ssl,mbedtls,libustream-mbedtls,libmbedtls,wpad-basic-mbedtls,hostapd.wpad-basic-mbedtls}.*
rm -rf build_dir/target-*/root-ipq806x
rm -f bin/packages/*/base/{libustream-mbedtls,libmbedtls12}*
make defconfig && make -j$(nproc)
```

## Flash procedure (briefly)

Stock OpenWrt `sysupgrade` is a no-op on this device — the platform.sh
case for `synology,rt2600ac` is missing, so it falls through to
`default_do_upgrade` which writes to a `firmware` MTD partition that
doesn't exist on this eMMC-based unit.  Flash manually.

### Partition layout (eMMC, after our v2 build is committed)

| Partition | Filesystem | Contents | Flash with |
|---|---|---|---|
| `mmcblk0p1` | ext4 | files: `zImage`, `rd.bin`, `dtb.dtb` | `mount` + replace files (NOT raw `dd`) |
| `mmcblk0p5` | squashfs (raw) | rootfs | raw `dd` |
| `mmcblk0p6` | ext4 | overlay (`/overlay`) | leave alone unless re-init needed |

> **Do not `dd` raw kernel data onto `/dev/mmcblk0p1`.** That partition
> is ext4. Synology's stock U-Boot bootcmd is
> `ext4load mmc 0:1 0x44000000 zImage; ext4load mmc 0:1 0x46000000 rd.bin; ext4load mmc 0:1 0x48000000 dtb.dtb; bootipq`,
> so it expects three files inside the filesystem. `dd` over the partition
> wipes the fs and the device hangs in U-Boot with "Failed to mount ext2
> filesystem" on next boot. Recover by mkfs.ext4-ing it from initramfs
> and writing the three files back (procedure below).

### Step-by-step (live router → new build)

1. **TFTP-boot the v2 initramfs from U-Boot.** The Synology stock U-Boot
   does NOT support `bootm` (no FDT/ATAGS) — use `bootipq`, and the
   image must be uImage format (the build's
   `openwrt-ipq806x-generic-synology_rt2600ac-initramfs-kernel.bin`):
   ```
   setenv ipaddr 192.168.1.1
   setenv serverip <your TFTP host>
   tftpboot 0x44000000 initramfs.bin
   bootipq
   ```
   *First `tftpboot` may report `Mac1/Mac2 unit failed` — retry, the PHY
   needs a beat to settle.*
2. From the initramfs prompt, bring LAN up on `eth1` (the bench cable
   path goes through the switch chip, not the WAN-port `eth0` that the
   default `/etc/config/network` puts in `br-lan`):
   ```
   ip link set br-lan down; ip addr flush dev br-lan
   ip link set eth1 up; ip addr add 192.168.1.1/24 dev eth1
   /etc/init.d/firewall stop
   ```
3. Pull the new artifacts from your host (HTTP / TFTP / scp).
4. Flash kernel files into `mmcblk0p1` (NOT raw `dd`):
   ```
   mkfs.ext4 -F -L kernel /dev/mmcblk0p1   # only if filesystem is fresh/wiped
   mkdir -p /mnt/p1 && mount /dev/mmcblk0p1 /mnt/p1
   wget http://HOST/zImage   -O /mnt/p1/zImage
   wget http://HOST/dtb.dtb  -O /mnt/p1/dtb.dtb
   wget http://HOST/rd.bin   -O /mnt/p1/rd.bin     # 576-byte placeholder is fine
   sync && umount /mnt/p1
   ```
5. Flash squashfs to `mmcblk0p5` (raw `dd` IS correct here):
   ```
   wget http://HOST/root.squashfs -O /tmp/root.squashfs
   dd if=/tmp/root.squashfs of=/dev/mmcblk0p5 bs=1M conv=fsync
   sync && reboot -f
   ```
6. **First boot of a fresh squashfs falls back to a tmpfs overlay.**
   The previous overlay was stamped with the *old* squashfs UUID; the
   new squashfs has a new UUID, so the extroot block-tool refuses to
   mount `mmcblk0p6` and you boot with default config (no LuCI password,
   default `OpenWrt` SSID). Two options:
   - **Keep existing user config** — update the stamp in place:
     ```
     mkdir -p /mnt/p6 && mount /dev/mmcblk0p6 /mnt/p6
     NEWUUID=$(blkid /dev/mmcblk0p5 | sed -n 's/.*UUID="\([^"]*\)".*/\1/p')
     printf %s "$NEWUUID" > /mnt/p6/etc/.extroot-uuid       # NO trailing newline
     sync && umount /mnt/p6 && reboot -f
     ```
     **The `printf %s` (not `echo`) matters.** `block` does a byte-exact
     compare of the stamp file against the rootfs UUID; a trailing
     newline gives you the maddening log line
     `extroot: UUID mismatch (root: a99e..., overlay: a99e...)` —
     same UUID, still rejected.
   - **Wipe and start fresh** — `mkfs.ext4 -F -U 09556310-5e0e-4879-affd-31f2ba325d56 -L overlay /dev/mmcblk0p6`,
     then reboot. Loses all `/etc/config` edits.

### About the kernel-with-appended-DTB

The build's `zImage` carries the DTB appended at the tail. The
standalone `dtb.dtb` file on `mmcblk0p1` is what U-Boot loads at
0x48000000 for `bootipq`'s reference but the running kernel actually
uses the DTB embedded in its own image. So: re-flash `zImage` after
any DTS change. Editing only the standalone `dtb.dtb` does nothing.
