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
| `logs/` | decoded boot logs and diagnostics of the bring-up |

## Rules learned the hard way

- **Untimed images are fine while SSH over the RNDIS gadget works**: leave with
  `ssh root@172.16.42.1 reboot` (init arms INFORM3=normal, so it lands in the downstream
  Debian). If a change could break USB/SSH, add `BOOTARGS_EXTRA="j4.bootreboot=180"`:
  a held power button does not reliably leave RECOVERY, and a stranded phone needs TWRP.
- Read device registers from the downstream kernel only at *defined* offsets: a hole
  in a CMU stalls the bus.
- S-BOOT zeroes `0x7e280000-0x7e2fffff` at every boot, so ramoops stays below it.
- Never install units or other persistent hooks in the rootfs from these tools.

## Typical loop

    BOOTARGS_REMOVE="j4.autoreboot=45" ./pack.sh   # untimed; add BOOTARGS_EXTRA="j4.bootreboot=180" for risky changes
    ./test-mainline.sh flash && ./test-mainline.sh reboot
    # SSH to root@172.16.42.1 works while mainline runs; `ssh root@172.16.42.1 reboot`
    # returns to the downstream Debian; `journalctl -b -1` holds the logs

`pylib/` (reedsolo) is not tracked: `pip install --target mainline-tools/pylib reedsolo`.
