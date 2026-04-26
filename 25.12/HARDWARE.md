# Hardware Notes — 25.12 port

Verified live on running OpenWrt 25.12.2 in April 2026. Read alongside `../23.05/HARDWARE.md` for things that didn't change (chipsets, UART pinout, machid).

## Corrections to the 23.05 DTS

These came from probing stock Synology SRM on the unit used for this port:

- **Reset button + WPS button GPIOs** were guesses in the 23.05 DTS; verified pin numbers in this DTS.
- **Status LED** wiring confirmed; the `led-running` / `led-failsafe` triggers in DTS match what stock SRM drove.
- **Third GMAC**: 23.05 DTS left `gmac0` enabled as a placeholder; verified unused at the board level — left disabled to avoid a phantom `eth2` netdev.
- **SD card slot** (back of unit): `cd-gpios` is pin 63 ACTIVE_LOW with `cd-inverted`, `bus-width = <4>` (overrides mainline default of 8). Verified by inserting a card on running SRM and watching the cd line.

## eMMC partition layout (final)

```
mmcblk0p1   16 MiB    ext2          OpenWrt boot recovery (mirror of p3)
mmcblk0p3   16 MiB    ext2          OpenWrt boot primary  — boots zImage
mmcblk0p4    1 KiB    -             extended-marker (synology vestige)
mmcblk0p5    1.2 GiB  squashfs+     OpenWrt rootfs recovery (mirror of p7 first 256 MiB)
mmcblk0p6    2.0 GiB  ext4          OpenWrt overlay (writable layer, UUID-mounted)
mmcblk0p7    256 MiB  squashfs      OpenWrt rootfs primary
```

p1, p3, p5, p7 are the four "boot slots." p2 / extended marker / large unused space between p7 and end-of-eMMC is left untouched. We do not write the eMMC `boot0` / `boot1` hardware boot regions.

## SPI NOR (MTD) layout

```
mtd0   0:sbl1          128 KiB   secondary boot loader 1
mtd1   0:mibib          128 KiB   memory init binary block
mtd2   0:sbl2          256 KiB   secondary boot loader 2
mtd3   0:sbl3          512 KiB   secondary boot loader 3
mtd4   0:ddrconfig     64 KiB    DDR training params
mtd5   0:ssd            64 KiB
mtd6   0:tz            512 KiB   TrustZone
mtd7   0:rpm           512 KiB   resource power manager
mtd8   0:appsbl        512 KiB   apps bootloader (this is U-Boot)
mtd9   0:appsblenv     256 KiB   U-Boot env
mtd10  0:art           256 KiB   wifi calibration data (no MACs at offset 0)
mtd11  0:vendorpart    832 KiB   Synology custom — MACs + serial + PIN
mtd12  0:fis           64 KiB
```

## MAC address layout (`0:vendorpart`)

Five sequential factory MACs starting at offset **0xd0**, 7-byte stride (6 MAC bytes + 1 tag byte after each). The pattern across units (Synology OUI `00:11:32`, last byte increments +1):

```
0xd0  00:11:32:XX:XX:N+0  T+0   ← MAC0  (lan / br-lan)
0xd7  00:11:32:XX:XX:N+1  T+1   ← MAC1  (wan)
0xde  00:11:32:XX:XX:N+2  T+2   ← MAC2  (radio0 / 5 GHz)
0xe5  00:11:32:XX:XX:N+3  T+3   ← MAC3  (radio1 / 2.4 GHz)
0xec  00:11:32:XX:XX:N+4  T+4   ← MAC4  (reserved)
```

`XX:XX:N` is the per-unit factory base (varies between units). The trailing tag byte (`T+0..T+4`) is also sequential — appears to be a port-id marker; we don't use it.

`0:vendorpart` also contains:
- Serial number string `SN=...,CHK=...` at offset 0x10
- PIN string `PIN=...,CHK=...` at offset 0x150

`0:art` is **not** the MAC source on this board — its offset 0 is blank (`0xff`). Calibration data lives at offsets 0x1000 (radio0) and 0x5000 (radio1) and is loaded fine; only MAC extraction uses vendorpart.

## ath10k calibration

Same as the 23.05 port: `0:art` offsets 0x1000 (12064 bytes) for radio0, 0x5000 (12064 bytes) for radio1. Loaded via OpenWrt's `caldata_extract` hotplug handler. We patch the per-radio MAC into the cal data after extraction (`ath10k_patch_mac` in `etc/hotplug.d/firmware/11-ath10k-caldata`).

## Regulator stack (the gotcha)

`mmci-pl18x` (eMMC controller at `12400000.mmc`) has a probe-ordering race with the IPQ806x regulator framework on stock kernel 6.12. The eMMC voltage rail (`vsdcc_fixed`) isn't fully registered when the controller asks for its voltage, so `mmci-pl18x` bails with `no support for card's volts` and the controller wedges. The 3 kernel reverts in `patches/` (against commits `b8c325545714`, `401d078eaf2e`, `a1d12410d9b1`) mostly fix this — primary autoboot is 5/5 reliable in stress test — but the race window isn't fully closed; manually invoking the recovery boot path can still trip it. See TROUBLESHOOTING.md. Upstream fix is `304f5784e972` which lands in kernel 7.0.
