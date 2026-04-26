# Troubleshooting

Major issues hit during the project and the actual fixes used:

## ninja Python 3.13 `pipes` import breakage

`tools/ninja` failed on Debian 13 / Python 3.13 because `pipes` was removed. Fixed by replacing `pipes.quote()` with `shlex.quote()`.

## cpio host configure fix

The host-side cpio toolchain also needed a local fix during build bring-up. The reconstructed note patch is included in this archive.

## Root-owned build artifacts blocking rebuild

Incremental rebuilds failed until stale root-owned files in `build_dir` were fixed with:

```bash
sudo chown -R "$USER:$USER" ~/openwrt/build_dir/
```

## USB storage missing from initramfs

Earlier images could not boot correctly from USB because storage support was not in the image. The fix was to include:
- `kmod-usb-storage`
- `kmod-usb3`
- related USB support packages

## sysupgrade hanging at `Waiting for root device`

Trying to boot the sysupgrade image directly from USB was unreliable because the rootfs device was not ready when the kernel wanted it. The working path was split-kernel on `mmcblk0p1` and squashfs root on `mmcblk0p5`.

## ext4 not mountable from initramfs

The initramfs lacked ext4 support at one stage, so extroot setup could not be completed from the live recovery image. The final fix was to bake ext4 support into the built image.

## opkg kernel hash mismatch

Official kmods could not be installed because the custom build had a different kernel ABI hash from upstream package feeds. For kmods, the answer was to build from the local tree. For user-space packages, official feeds were still usable.

## bootargs not passing through `bootm`

Direct `bootm` tests did not reliably get `root=/dev/mmcblk0p5` into the kernel. This was part of why the final boot path uses `bootipq`.

## `fdt chosen` returning `FDT_ERR_NOSPACE`

Manual DT mutation required `fdt resize` first. This was diagnostic-only in the final flow.

## `bootipq` requiring a valid ramdisk format

`bootipq` refused to continue if `rd.bin` was missing or not a valid U-Boot ramdisk image. The workaround was an empty but valid uImage-wrapped ramdisk placeholder.

## Kernel hang after `fdt resize` + `bootm`

Using `fdt resize` with the manual `bootm` flow caused early kernel hangs. The final fix was not to rely on that path.

## `root=/dev/mmcblk0p5` not reaching the kernel

The final reliable fix was to hardcode:

```text
rootfstype=squashfs,ext4 rootwait noinitrd root=/dev/mmcblk0p5
```

directly into the DTS `chosen.bootargs`.

## Subnet conflict on `192.168.1.x`

Direct laptop-to-router work initially collided with the surrounding home network. The stable temporary development subnet was:
- `10.99.0.1/24` on router
- `10.99.0.2/24` on laptop

## NetworkManager interfering with direct Ethernet

The laptop Ethernet interface had to be taken out of NetworkManager control for deterministic direct-link tests:

```bash
nmcli device set <iface> managed no
```

## `eth1` vs `eth0`

On this board:
- physical LAN ports are on `eth1`
- WAN is `eth0`

This mattered for every direct-link recovery and extroot setup session.

## extroot `fstab` not persisting

The durable fix was to bake `/etc/config/fstab` into the squashfs image via:
- `files/etc/config/fstab`

so the first boot of the real rootfs had the correct extroot configuration.

## WiFi calibration / board data

This unit's ART data was not clean. The radios only stabilized once the board/calibration path was corrected so ath10k could use pre-cal data and valid board data instead of failing on `board-2.bin`.

