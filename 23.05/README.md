# RT2600ac OpenWrt

This archive captures the full working state of the Synology RT2600ac OpenWrt port as finished in March 2026. The goal was to replace Synology firmware on eMMC with OpenWrt 23.05.3, preserve a recoverable boot path, and move persistent writes onto USB extroot.

Current status:
- OpenWrt 23.05.3 is booting from eMMC on every reboot
- kernel lives on `mmcblk0p1`
- squashfs rootfs lives on `mmcblk0p5`
- extroot lives on USB `sda2` mounted at `/overlay`
- both QCA9984 radios enumerate and come up as APs
- WAN DHCP works on `eth0`
- LAN is `192.168.1.1/24 (or whatever subnet you prefer)`

Hardware summary:
- SoC: Qualcomm IPQ806x dual-core Cortex-A15
- RAM: 512 MB
- eMMC: Kingston M62704, ~3.5 GB
- WiFi: two QCA9984 hw1.0 radios
- Switch: Atheros AR8337
- UART: `ttyMSM0`, `115200 8N1`

Software summary:
- OpenWrt: 23.05.3
- Kernel: 5.15.150
- U-Boot: 2016.01

Quick start for a second identical unit:
1. Rebuild the same images from the instructions in [BUILD.md](./BUILD.md).
2. Catch the U-Boot prompt with [`scripts/catch_uboot.py`](./scripts/catch_uboot.py).
3. Boot initramfs once from USB.
4. Write boot files to `mmcblk0p1` and squashfs root to `mmcblk0p5`.
5. Boot OpenWrt from eMMC.
6. Set up extroot on `sda2`.
7. Save the permanent U-Boot boot command from [UBOOT.md](./UBOOT.md).

Known caveats:
- The original Synology ART/calibration state on this unit was damaged, so WiFi needed explicit board/calibration handling.
- `bootipq` is required for this board; plain `bootm` was not reliable for passing the right platform state.
- OpenWrt LAN was moved to `192.168.1.1/24 (or whatever subnet you prefer)` to avoid conflict with the upstream network used during development.
- The USB key is only used for extroot. The system boots from eMMC.

