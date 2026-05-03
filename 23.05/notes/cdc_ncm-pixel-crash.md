# Pixel 9 Pro / `cdc_ncm` probe crash — diagnosis log

If you plug a Google Pixel 9 Pro (USB ID `18d1:4eec`) with USB
tethering enabled into an OpenWrt 23.05.3 / kernel 5.15.150 system
that has the standard `kmod-usb-net-cdc-ncm`, the kernel oops's during
NCM bind and the watchdog reboots the box.  Trying the standard
"recompile cdc_ncm against the running kernel" fix doesn't help — the
problem isn't an ABI mismatch.

This is the writeup of how the trace was captured and how the fix in
`patches/780-usbnet-defensive-null-dev-addr.patch` was derived.

## Symptom

- USB enumerates fine while the phone is in ADB-only mode (one
  interface, vendor-specific class 0xff).
- The moment USB tethering is toggled on, the phone re-enumerates with
  three interfaces:

  ```
  3-1.4:1.0  class=ff sub=42         (ADB)
  3-1.4:1.1  class=02 sub=0d         (NCM)
  3-1.4:1.2  class=0a sub=00         (CDC Data)
  ```

- The kernel matches `cdc_ncm` against interface 1.1.  The bind path
  through `usbnet_probe()` triggers a NULL pointer dereference and
  the procd watchdog reboots the system before serial flushes any
  trace.

## Capturing the crash without a watchdog reboot

```sh
# Disable procd's watchdog so the kernel doesn't get force-rebooted
ubus call system watchdog '{"magicclose":true,"stop":true}'
# And don't auto-reboot on oops
echo 0 > /proc/sys/kernel/panic
echo 0 > /proc/sys/kernel/panic_on_oops
```

Then start a serial capture on the host (`/dev/ttyUSB0`, 115200 8N1)
and toggle tethering on the phone.

## The trace

```
Internal error: Oops: 805 [#1] SMP ARM
Modules linked in: pppoe ppp_async ... cdc_ncm cdc_ether usbnet ...
CPU: 0 PID: 88 Comm: kworker/0:3 Not tainted 5.15.150 #0
Workqueue: usb_hub_wq hub_event
PC is at _60+0x2ac/0x848 [usbnet]
LR is at 0x80808080
pc : [<bf20c814>]    lr : [<80808080>]    psr: 60000013
...
r3 : bf20f9c8   r2 : 00000000   r1 : bf20f8a9   r0 : <random>
...
Register r2 information: NULL pointer
Process kworker/0:3 (pid: 88, stack limit = 0xf7ce99c9)
[<bf20c814>] (_60 [usbnet]) from [<c074f9d8>] (usb_probe_interface+0x98/0x1ac)
[<c074f9d8>] (usb_probe_interface) from [<c06a28d8>] (really_probe.part.0+0x9c/0x324)
...
[<c0746fb4>] (hub_event) from [<c0336d10>] (process_one_work+0x210/0x478)
...
Code: e5942218 e5980000 e3a0cf7d e59f3588 (e5820000)
                                          ^^^^^^^^^
                                          str r0, [r2]   ← faulting insn
```

The function symbol shows up as `_60` because module symbols are
stripped in the OpenWrt build.  Resolution is straightforward from the
PC offset: the module base is at `0xbf20b000` (vmalloc region for
`usbnet.ko`), so the faulting PC `0xbf20c814` is at offset `0x1814`
into the `.text` section.  `arm-openwrt-linux-muslgnueabi-objdump -t
usbnet.ko` shows the function spanning that offset:

```
00001568 00000848 usbnet_probe
```

So `_60+0x2ac` = `usbnet_probe + 0x2ac`.

Disassembling around the PC:

```
1800: bl    <strscpy>                ; strscpy(net->name, "usb%d", ...)
1804: ldr   r2, [r4, #520]   @ 0x208 ; r2 = *(net + 0x208)  → net->dev_addr
1808: ldr   r0, [r8]                 ; r0 = *node_id (4 bytes of MAC)
180c: mov   ip, #500
1810: ldr   r3, [pc, #1416]          ; r3 = constant from .data
1814: str   r0, [r2]                 ; *r2 = r0   ← CRASH (r2 is NULL)
1818: add   r1, r3, #300
181c: ldrh  r0, [r8, #4]             ; r0 = node_id[4..5]
1820: strh  r0, [r2, #4]             ; *(r2 + 4) = r0
```

Cross-referencing with the source (`drivers/net/usb/usbnet.c`):

```c
strscpy(net->name, "usb%d", sizeof(net->name));
memcpy (net->dev_addr, node_id, sizeof node_id);   // ← faulting line
```

So the crash is on the very first MAC-address copy in `usbnet_probe`,
*before* `info->bind()` is called.  `net->dev_addr` (a pointer in
5.15-era `struct net_device`) is somehow NULL even though
`alloc_etherdev()` returned non-NULL.

## Why this is Pixel-specific (mostly)

In normal flow, `alloc_netdev_mqs()` calls `dev_addr_init()` which
allocates a `netdev_hw_addr` and sets `dev->dev_addr` to point at its
storage.  If that fails the alloc returns NULL and `usbnet_probe`
takes the `goto out` path, never touching the dereferenced field.

The fact that we land on the unguarded memcpy with a non-NULL `net`
but a NULL `net->dev_addr` is a kernel-internal state inconsistency.
We did not chase the exact root cause — it doesn't reproduce with the
USB stick or Realtek RTL8153 dongle on the same hub, only with the
Pixel.  Likely candidates: a netdev allocation race during the hub
event handler that fires on Android's quick disconnect/reconnect when
tether mode toggles, or a config-dependent layout interaction.

## The fix

`patches/780-usbnet-defensive-null-dev-addr.patch` guards the memcpy
with a NULL check.  When the pointer is unset, log a warning and skip
the initial copy.  The driver's `info->bind()` callback (in
`cdc_ncm_bind_common`, called shortly after) sets the MAC from device
descriptors, and `register_netdev()` falls back to a random address
with `NET_ADDR_RANDOM` if needed.

After applying the patch and rebuilding:

```
cdc_ncm 3-1.4:1.1: MAC-Address: 1a:74:26:25:a3:63
cdc_ncm 3-1.4:1.1 usb0: register 'cdc_ncm' at usb-xhci-hcd.1.auto-1.4, CDC NCM
```

`usb0` appears as a normal netdev, DHCPs from the phone's tether-NAT
range, default route flips through it, traffic flows.

## A separate USB-power gotcha

The same Pixel 9 Pro will not enumerate at all when plugged directly
into the RT2600ac's USB ports — the device requests ~1.5 A for fast
charge and the host port can't supply it, producing
`device descriptor read/8, error -71` in an infinite reset loop.  Use
a powered USB hub between the phone and the router and the
enumeration succeeds (after which this kernel patch is also needed
for tethering to actually work).
