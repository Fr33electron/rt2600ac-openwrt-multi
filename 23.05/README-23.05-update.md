# Suggested edits to existing 23.05/README.md

The current 23.05/ README describes the v1 port (USB extroot).  Below is a
suggested replacement section, leaving everything else as-is.  Drop in
where the old "Key features" block lived.

---

## Key features (v2, May 2026)

- Boots from eMMC via Synology's stock U-Boot using `bootipq` (kernel +
  ramdisk + DTB at three load addresses; ext4 files on `mmcblk0p1`)
- Squashfs rootfs on `mmcblk0p5` (raw, what `dd` writes)
- **Persistent overlay on `mmcblk0p6` (eMMC ext4)** — no USB stick required
  for boot
- **SD card slot live as `mmc1`** (`12180000.sdcc`, CD GPIO 63)
- **USB-net drivers in firmware** — `cdc_ether`, `cdc_ncm`, `ipheth`,
  `rndis_host`, `usbnet`
- **`e2fsprogs`** (`mkfs.ext4`, `e2fsck`, `dumpe2fs`) baked in
- **LuCI web UI baked in** — `luci`, `luci-ssl-openssl` (HTTPS on :443),
  `luci-app-firewall`, `luci-app-opkg`. wpad pinned to `wpad-basic-openssl`
  to avoid the libustream-mbedtls vs libustream-openssl file clash.
- WiFi calibration extracted from this unit's own ART via the
  `synology,rt2600ac` recipe ported from upstream 25.12 into
  `target/linux/ipq806x/base-files/etc/hotplug.d/firmware/11-ath10k-caldata`
  (mainline 23.05 lacks this case for the board)
- Works as a self-contained gateway over USB tether (Pixel-class NCM
  devices) when paired with the in-tree usbnet patch — see
  `patches/780-usbnet-defensive-null-dev-addr.patch`

## What changed from v1

- **v1:** extroot overlay on USB `sda2`; SD slot not in DTS; no USB-net
  drivers; no LuCI; sysupgrade left as a no-op (default platform.sh
  fall-through); pre-cal files hand-staged into the build
- **v2:** overlay migrated to eMMC `mmcblk0p6`; SD slot ported from the
  unit-2 DTS (with corrected CD polarity and `vmmc-supply` added);
  USB-net + `e2fsprogs` + LuCI baked in; in-tree patch fixes Pixel 9 Pro
  NCM bind crash; `11-ath10k-caldata` extracts cal from the board's own
  ART partition at boot

See [`CHANGELOG-v2.md`](./CHANGELOG-v2.md) for the full diff and flash
procedure, and [`notes/cdc_ncm-pixel-crash.md`](./notes/cdc_ncm-pixel-crash.md)
for the kernel-trace walkthrough that produced the patch.
