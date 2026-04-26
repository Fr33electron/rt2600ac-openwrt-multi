# Troubleshooting — unit 2

The major issues hit during this port, with what actually fixed each.

## `mmci-pl18x: no support for card's volts` at every cold boot

**Symptom**: lean (non-initramfs) kernel boots U-Boot fine, hands off to kernel, kernel starts probing, then in dmesg:

```
[    2.846] Waiting for root device /dev/mmcblk0p7...
[    2.981] mmc0: Card stuck being busy! __mmc_poll_for_busy
[    3.015] mmci-pl18x 12400000.mmc: no support for card's volts
[    3.015] mmc0: error -22 whilst initialising SDIO card
```

System hangs at "Waiting for root device". Initramfs kernel works, lean kernel doesn't.

**Root cause**: regulator probe-ordering race. Three commits in mainline kernel's regulator tree changed how OF lookups for fixed-voltage regulators work, and that exposed a window where `mmci-pl18x` asks the regulator framework for `vsdcc_fixed`'s voltage before the regulator is fully registered. The CPIO decompression delay in initramfs kernels masks the race; lean kernels don't have that delay.

**Fix**: revert three commits (in the right order — they have textual dependencies):

```
0991-Revert-regulator-core-fix-the-broken-behavior-of-reg.patch  → commit a1d12410d9b1
0992-Revert-regulator-of-Refactor-of_get_-regulator-to-de.patch  → commit 401d078eaf2e
0993-Revert-regulator-Move-OF-specific-regulator-lookup-c.patch  → commit b8c325545714
```

These live in `patches/` and drop into `target/linux/ipq806x/patches-6.12/`. With them applied, primary autoboot is reliable (5/5 cold-boot stress test).

The proper upstream fix is `304f5784e972` ("regulator: Honor regulator-boot-on for fixed regulators"), which lands in kernel 7.0. Drop the three reverts when OpenWrt picks up that kernel.

## bootcmd chain `run bootemmc || run bootmmc` does not auto-fall-back

**Symptom**: with `bootcmd=run bootemmc || run bootmmc` saved, deliberately corrupting p3 (rename `/zImage` → `/zImage.disabled` so `ext2load mmc 0:3 zImage` fails) does **not** cause U-Boot to fall through to `bootmmc`. Cold boot leaves the system stuck — no boot from either p3 (corrupted) or p1 (chain didn't trigger).

**Root cause** (likely): U-Boot 2012.07's `||` operator doesn't propagate inner-command failure through `run`. When `bootemmc` env contains `mmc rescan; ext2load mmc 0:3 $kload zImage; bootm $kload` and `ext2load` fails, the failure stops the inner chain but `run` itself returns success-ish — so the outer `||` never fires.

**Workarounds** (untested but standard):
- **`altbootcmd` + `bootcount`** — U-Boot's built-in mechanism. Set `bootcount=0` in env, set `bootlimit=3`, set `altbootcmd=run bootmmc`. After 3 failed boots (where boot doesn't reset bootcount), U-Boot runs `altbootcmd` instead of `bootcmd`. Need to wire boot-success bootcount-reset somewhere on the OpenWrt side too.
- **Explicit file test** — `bootcmd=ext2load mmc 0:3 $kload zImage && bootm $kload ; run bootmmc`. The `&&` between the load and bootm short-circuits properly because both are top-level u-boot commands, not `run`-ed env vars.

**Manual recovery in the meantime**: catch U-Boot via serial, `ext2load mmc 0:1 0x44000000 zImage`, `bootm 0x44000000` — this works reliably with normal command pacing (single-second between commands). The recovery slot itself (p1 kernel, p5 rootfs) is bootable; only the auto-trigger is missing.

## Recovery boot from `mmcblk0p1` still hits the regulator race occasionally

**Symptom**: primary autoboot via `bootemmc` is reliable, but invoking `run bootmmc` manually after sitting at the U-Boot prompt for several seconds has triggered the same volts/stuck error at least once.

**Hypothesis**: the 3-revert patch reduces but does not eliminate the race. Sitting at the U-Boot prompt longer (several seconds) before invoking the boot command appears to expose a wider timing window than autoboot does, possibly due to the eMMC controller's idle/active state transitions.

**Status**: not yet fully understood. Practical impact: automatic failover via `bootcmd=run bootemmc || run bootmmc` should still work because it triggers immediately after `bootemmc` failure with no idle time at the prompt. Manual `run bootmmc` from a held prompt is less reliable.

**Suggested next step**: cold-boot 5–10 times, catch U-Boot, immediately run `bootmmc` (no extra delay), measure failure rate. Compare with bootmmc-after-Nseconds-at-prompt to characterize timing sensitivity. Possibly add a `mmc rescan; sleep 2; mmc rescan` in the env as a workaround.

## Wifi APs broadcast with placeholder MAC `12:34:56:78:90:12`

**Symptom**: after first boot, `iwinfo phy0-ap0` shows BSSID `12:34:56:78:90:12` and `phy1-ap0` shows `00:03:7f:12:34:56`. Eth interfaces show random LAA MACs.

**Root cause**: this board does not have MACs at the expected `0:art` offset 0; that whole region is `0xff`. Synology stores the factory MACs in `0:vendorpart` at offset 0xd0, in 5 sequential records with a 7-byte stride. The default OpenWrt `ipq806x_setup_macs` doesn't know this layout.

**Fix**: add a board case to `etc/board.d/02_network` to extract the MAC and `ucidef_set_interface_macaddr` for lan/wan. Add `ath10k_patch_mac` calls in `etc/hotplug.d/firmware/11-ath10k-caldata` for both radios. Add a `etc/uci-defaults/05_set_synology_macs` script for first-boot device-level macaddr (because `board.json` macaddr doesn't propagate to `/etc/config/network` device entries automatically once the network UCI exists).

All three files are in `files/etc/` in this archive.

## `iwinfo` shows STA encryption as "none" but uplink works fine

**Symptom**: after configuring a wifi-iface in `mode=sta` to associate with a WPA2 AP, `iwinfo phy1-sta0` reports `Encryption: none`. The link is otherwise healthy — 200+ Mbps, signal strong, traffic flowing.

**Root cause**: `iwinfo` reads encryption state differently for AP-mode (asks hostapd) vs STA-mode (probes nl80211 directly). When wpa_supplicant handles the crypto upstairs, the nl80211 probe doesn't see a hostapd-style cipher mapping and falls back to "none."

**It's a display bug, not a real issue.** Confirm by reading `/var/run/wpa-supplicant-phy1-sta0.conf` — `key_mgmt=WPA-PSK proto=RSN psk="..."` will be there if wpa_supplicant is doing the right thing.

## `bootipq` panics after we got the kernel onto p3

**Symptom**: U-Boot loads zImage + rd.bin + dtb.dtb at the standard 0x44 / 0x46 / 0x48 addresses, runs `bootipq`, kernel starts but immediately panics or wedges.

**Root cause**: this kernel build has an **appended DTB** — concatenated to the end of the zImage. The external DTB at 0x48000000 conflicts with it; the kernel sees two DTBs and reads the wrong one.

**Fix**: switched the boot env to single-arg `bootm $kload` (no rd, no external DTB). U-Boot leaves the kernel to find its own appended DTB. See UBOOT.md.

## `block: unable to load configuration (fstab: Entry not found)` early in dmesg

**Symptom**: every boot logs:

```
user.err kernel: block: unable to load configuration (fstab: Entry not found)
```

Always exactly twice, before fstab UCI is fully loaded.

**Status**: cosmetic. The `block` tool runs at preinit before `/etc/config/fstab` is necessarily in its final state; the error refers to attempted automatic mounts of partitions without UCI entries. Real fstab service starts later and mounts the configured entries successfully (`/mnt/data` shows up correctly). Not worth chasing.

## odhcpd: `No default route present, setting ra_lifetime to 0`

**Symptom**: odhcpd warns about no default route at startup.

**Status**: expected. Without WAN, there is no default route. As soon as wwan associates (~165 s after cold boot in our setup), the warning clears.

## dnsmasq: `no servers found in /tmp/resolv.conf.d/resolv.conf.auto`

**Symptom**: dnsmasq retries finding upstream DNS at boot.

**Status**: expected during the gap between dnsmasq starting and wwan association completing. Resolves itself.

## SCP to router fails with `/usr/libexec/sftp-server: not found`

**Symptom**: `scp file root@router:/path/` errors with sftp-server not found.

**Root cause**: OpenWrt's busybox dropbear doesn't ship a sftp-server, and modern OpenSSH `scp` uses the SFTP protocol by default.

**Fix**: either `scp -O` (force legacy SCP protocol) or pipe through `cat` — `cat localfile | ssh router 'cat > /path/file'` works fine. We used the cat-pipe approach for our deploy scripts.

## `eth0` and `eth1` MACs are still random LAA values after MAC fix

**Symptom**: after the MAC fix, `br-lan` and `wan` show factory MACs from vendorpart, but `eth0` (`8e:...`) and `eth1` (`66:...`) still show random LAA addresses.

**Status**: cosmetic. eth0 and eth1 are the DSA conduit / CPU ports; they're not user-facing. Peers see the bridge or wan port MAC, never the underlying CPU port. Setting macaddr on `network.@device[0]` (br-lan) and `network.wan_dev` (wan) is sufficient.

## eMMC partition table reported as "Invalid" by U-Boot

**Symptom**:

```
GUID Partition Table Header signature is wrong:0x0 != 0x5452415020494645
find_part_efi: *** ERROR: Invalid Primary GPT ***
```

**Root cause**: this U-Boot expects a GPT but Synology used MBR-style partitioning. U-Boot prints the warning and falls back to its own SMEM-based partition table. eMMC is fully usable; the warning is just U-Boot complaining about a partitioning style it doesn't recognize.

**Status**: ignore.
