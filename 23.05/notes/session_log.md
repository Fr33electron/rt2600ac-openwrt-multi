# Session Log

## Timeline

1. Identified the USB serial dongle on the Debian laptop and confirmed console access at `115200 8N1`.
2. Verified control of the Siglent SPD3303X PSU over SCPI.
3. Fresh-cloned OpenWrt 23.05.3 on Debian 13 as a regular non-root user.
4. Added the custom `synology_rt2600ac` target and DTS.
5. Fixed host build blockers on Debian 13:
   - ninja Python 3.13 `pipes` removal
   - host cpio compatibility issue
   - root-owned build artifacts left by mixed-root steps
6. Built initial images and iterated on image layout:
   - discovered Synology `bootmmc` expects named files on ext4
   - reconstructed `mmcblk0p1` as ext4 with `zImage`, `rd.bin`, `dtb.dtb`
7. Determined that initramfs boot could not support final extroot goals.
8. Split the sysupgrade image:
   - kernel into boot partition
   - squashfs rootfs into `mmcblk0p5`
9. Found that `root=/dev/mmcblk0p5` was not reaching Linux through runtime bootargs.
10. Hardcoded the final root argument into the RT2600AC DTS `chosen.bootargs`.
11. Achieved stable OpenWrt boot from eMMC.
12. Added ext4/block support and baked extroot `fstab` into the image.
13. Formatted `sda2` and confirmed extroot switched successfully.
14. Saved the permanent U-Boot `bootcmd`.
15. Moved LAN to `192.168.1.1/24`, configured WiFi, installed LuCI and utilities, and set the root password.
16. Verified unattended reboot with:
   - eMMC boot
   - extroot mounted
   - WiFi APs up
   - WAN internet working

## Key decisions

### Use `bootipq`

This board behaved like a Qualcomm IPQ platform first and a generic U-Boot board second. Final reliability came from using `bootipq` and feeding it a valid kernel, DTB, and placeholder ramdisk.

### Boot from eMMC, write to USB only for overlay

The final architecture is:
- `mmcblk0p1`: boot files
- `mmcblk0p5`: squashfs root
- `sda2`: extroot

This keeps the boot path deterministic and limits USB dependence to writable overlay storage.

### Bake persistent config into squashfs

Trying to repair extroot only from the live overlay was fragile. Baking `files/etc/config/fstab` into the image made first boot deterministic.

## Second-unit deployment expectation

If the second unit is electrically similar and has accessible serial + PSU control, expected deployment time is roughly:
- 30 to 45 minutes if reusing the built images
- longer only if the second unit has different calibration/MAC/ART behavior

Expected second-unit flow:
1. Catch U-Boot
2. Boot initramfs once
3. Write `boot.img` to `mmcblk0p1`
4. Write squashfs rootfs to `mmcblk0p5`
5. Boot OpenWrt from eMMC
6. Set up extroot on `sda2`
7. Save bootcmd
8. Configure LAN/WAN/WiFi

