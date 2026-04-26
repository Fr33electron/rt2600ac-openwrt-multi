# Hardware Notes

Verified platform details:

- SoC: Qualcomm IPQ806x dual-core ARM Cortex-A15, nominal 1.4 GHz class
- RAM: 512 MB
- eMMC: Kingston M62704, about 3.5 GB
- WiFi:
  - 5 GHz radio: QCA9984 hw1.0 on PCIe controller `1b500000`
  - 2.4 GHz radio: QCA9984 hw1.0 on PCIe controller `1b700000`
- Ethernet switch: Atheros AR8337
- USB: 2x USB 3.0 xHCI controllers
- UART:
  - device: `ttyMSM0`
  - settings: `115200 8N1`
  - logic level: 2.5 V
  - physical note: ground and RX were swapped from the original expectation on the 6-pin header
- machid: `0x136c`
- SPI NOR: 8 MB MX25U6435F
- ART state on this unit: erased/damaged; MAC and WiFi calibration had to be worked around

Original Synology WiFi calibration location:
- `/lib/firmware/QCA9984/hw.1/` on Synology firmware

eMMC partition map in final working state:
- `mmcblk0p1` 16 MB ext4
  - OpenWrt boot partition
  - contains `zImage`, `rd.bin`, `dtb.dtb`
- `mmcblk0p3` 16 MB ext2
  - Synology rescue
  - left intact
- `mmcblk0p5` ~1.2 GB squashfs
  - OpenWrt rootfs
- `mmcblk0p6` ~2 GB ext4
  - unused in final layout
  - formerly Synology runtime
- `mmcblk0p7` ~256 MB ext4
  - unused in final layout
  - formerly Synology factory restore

USB key final use:
- `sda1`: not used by the running system
- `sda2`: extroot overlay mounted at `/overlay`

