# Mainline (linux-7.2.y) bring-up tools for the Galaxy J4

Everything here drives the mainline port of the Exynos7570 in `../linux-7.2.y`
(branch `exynos7570-mainline`). The downstream 3.18 kernel and the Debian
rootfs on SYSTEM stay the working system; mainline test images live in the
RECOVERY partition and are booted with `reboot recovery`.

| file | purpose |
| --- | --- |
| `build.sh` | build the kernel with LLVM in the `j4-mainline` container (`build-mainline/`) |
| `j4-mainline.config` | tracked config fragment merged onto the arm64 defconfig |
| `pack.sh` | wrap Image + dtb + initramfs into a uniLoader boot image (`IMAGE`, `DTB`, `RAMDISK`, `PAYLOAD_ENTRY`, `BOOTARGS_EXTRA`, `BOOTARGS_REMOVE` override) |
| `test-mainline.sh` | `flash` / `reboot` / `dump` / `run` the test loop over SSH (RECOVERY = mainline image) |
| `restore-twrp.sh`, `restore-debian-boot.sh` | put TWRP back into RECOVERY / the Debian image back into BOOT |
| `ramoops_parse.py` | decode a ramoops dump (with Reed-Solomon ECC) |
| `ramretain/`, `regpeek/` | downstream-kernel modules: keep/dump a RAM window, read device registers |
| `clkgen/` | generates `clk-exynos7570.c` and its binding header from the downstream pwrcal tables |
| `uniloader/load-kernel.c` | uniLoader hand-off with cache maintenance and diagnostics |
| `logs/` | decoded boot logs and diagnostics of the bring-up |

## Rules learned the hard way

- **Every mainline image must end by itself.** Use `BOOTARGS_EXTRA="j4.bootreboot=180"`
  (or `j4.autoreboot=N` for the read-only test mode). A held power button does not
  reliably leave RECOVERY, so an untimed image can strand the phone until TWRP is
  flashed again.
- Read device registers from the downstream kernel only at *defined* offsets: a hole
  in a CMU stalls the bus.
- S-BOOT zeroes `0x7e280000-0x7e2fffff` at every boot, so ramoops stays below it.
- Never install units or other persistent hooks in the rootfs from these tools.

## Typical loop

    BOOTARGS_REMOVE="j4.autoreboot=45" BOOTARGS_EXTRA="j4.bootreboot=180 j4.diag=1" ./pack.sh
    ./test-mainline.sh flash && ./test-mainline.sh reboot
    # SSH to root@172.16.42.1 works while mainline runs; the phone returns to the
    # downstream Debian by itself, /root/j4-diag-*.txt and `journalctl -b -1` hold the logs

`pylib/` (reedsolo) is not tracked: `pip install --target mainline-tools/pylib reedsolo`.
