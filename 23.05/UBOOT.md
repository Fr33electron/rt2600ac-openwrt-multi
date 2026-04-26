# U-Boot Notes

## Catching the prompt

Use the prompt-aware catcher:
- [`scripts/catch_uboot.py`](./scripts/catch_uboot.py)

It watches serial output for:
- `Press Ctrl+C to abort autoboot`

and sends a single `Ctrl+C`, then confirms the U-Boot prompt (`IPQ806x#`) instead of spamming input.

## Verified load addresses

- `kload=0x44000000`
- `rload=0x46000000`
- `dload=0x48000000`

## Permanent boot command

Final saved `bootcmd`:

```text
ext4load mmc 0:1 0x44000000 zImage; ext4load mmc 0:1 0x46000000 rd.bin; ext4load mmc 0:1 0x48000000 dtb.dtb; bootipq
```

## Why `bootipq` and not `bootm`

This platform expects the Qualcomm IPQ boot flow. Plain `bootm` was usable for some manual tests, but it did not consistently preserve the platform-specific behavior needed on this board. `bootipq` was the stable choice once the boot partition contained:
- a valid kernel image
- a valid `rd.bin` ramdisk image
- a valid DTB

## Why `fdt resize` matters

When manually experimenting with `fdt chosen`, U-Boot returned:
- `FDT_ERR_NOSPACE`

Running `fdt resize` first allowed `fdt chosen` to write bootargs into `/chosen`. This was useful for diagnosis, but not the final boot path.

## bootmmc behavior

The stock Synology `bootmmc` flow loads named files from `mmc 0:1`:
- `zImage`
- `rd.bin`
- `dtb.dtb`

It does not boot a raw blob from the start of the partition. That is why the ext4 boot partition had to be reconstructed with those filenames.

## MAC address warning

This unit shows repeated U-Boot warnings about MAC addresses because the original ART state was damaged. The running system ultimately relies on environment/default values rather than pristine factory ART data.

