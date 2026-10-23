# Modem bring-up analysis — Shannon CP on mainline (Exynos7570, Galaxy J4)

**Status (2026-10-23): unblocked.** The EL3 CP-control service returns `0xb` for
CP_CTRL reads on downstream too until the CP has been booted (image verified by mode 0);
after that the reads work. Mainline is not the cause: it needs the full boot sequence
(images into the carveout, mode 0, power on). See "Downstream probe (2026-10-23)".

Sources: downstream 3.18 tree (`kernel/`), mainline tree (`linux-7.2.y/`),
libsamsung-ipc (`libsamsung-ipc/samsung-ipc/devices/herolte/herolte.c`), and a probe
module run on the mainline phone. Unverified points are marked **(unverified)**.

## Goal and approach

Keep the downstream userspace ABI (`/dev/umts_boot0`, `/dev/umts_ipc0`, `rmnet0`) so
samsungipcd, libsamsung-ipc's herolte CP boot path and the `samsungipcd` MM plugin work
unchanged. A proper `drivers/net/wwan` driver can come later; no WWAN port type is known
to fit Samsung IPC framing **(unverified)**.

## What mainline already has

- Modem carveout reserved: `modem@73400000`, size `0x5c00000` (92 MiB), `no-map` in
  `exynos7570-j4lte.dts`, same address as downstream `exynos7570-rmem.dtsi`
  (`exynos,modem_if`).
- PMU syscon, pinctrl, clocks, eMMC (RADIO p12 and `/efs/nv_data.bin` readable), PSCI
  SMCs reach EL3, `CONFIG_MODULES=y` (no modversions, no signing).
- Userspace CP boot needs no Samsung `cbd`: libsamsung-ipc `herolte.c` reads the TOC
  from RADIO and drives `umts_boot0` ioctls itself.

## Downstream pieces to port

| Piece | Downstream source | Size | Notes |
|---|---|---|---|
| CP power/reset/start | `drivers/soc/samsung/pmu-cp.c` | 447 | With `CONFIG_CP_SECURE_BOOT=y` every CP_CTRL access is an SMC, not a PMU write |
| CP mailbox | `drivers/misc/mcu_ipc/mcu_ipc.c` | 354 | `mailbox_cp` @0x10500000 size 0x180, SPI 369, `samsung,exynos-shd-ipc-mailbox`. Clock gate need unchecked |
| Shared-memory layout | `drivers/misc/mcu_ipc/shm_ipc.c` | 245 | Carveout offsets; also `shm_get_security_param2/3` |
| SIPC link + io devices | `drivers/misc/modem_v1/` | ~7k core | `link_device_shmem.c` 3062, `modem_io_device.c` 1518, `modem_main.c` 974, `modem_ctrl_ss310ap.c` 843, `link_device_memory_sbd.c` 662 |
| Board pdata | `arch/arm64/boot/dts/modem-ss305ap-pdata.dtsi` | 240 lines | `mif,name = "ss305ap"`, `LINKDEV_SHMEM`; iods `umts_ipc0/1`, `umts_rfs0`, `umts_csd`, `umts_router`, `umts_dm0`, `rmnet0-7`, `multipdp`, `umts_boot0`, `umts_ramdump0`, `smd4`, `umts_ciq0` |

Downstream kernel config: `CONFIG_MCU_IPC`, `CONFIG_SHM_IPC`, `CONFIG_SEC_SIPC_MODEM_IF`,
`CONFIG_SEC_MODEM_SS310AP`, `CONFIG_LINK_DEVICE_SHMEM`, `CONFIG_UMTS_MODEM_SS310AP`,
`CONFIG_CP_SECURE_BOOT` (all `=y`).

## Secure-world interface (from downstream source)

- `include/soc/samsung/pmu-cp.h`: `SMC_ID 0x82000700`, `READ_CTRL 3`, `WRITE_CTRL 4`;
  `enum cp_control { CP_CTRL_S = 0, CP_CTRL_NS = 1 }`. PMU offsets (for reference):
  CP_CTRL_NS 0x30, CP_CTRL_S 0x34, CP_STAT 0x38, CP_DEBUG 0x3c. Bits: CP_PWRON 1,
  CP_RESET_SET 2, CP_START 3, CP_ACTIVE_REQ_CLR 6, CP_RESET_REQ_CLR 8.
- `pmu-cp.c` `exynos_smc_read()`: `exynos_smc(SMC_ID, READ_CTRL, half, reg)` twice
  (half 0 = low 16 bits, 1 = high); success = bits 15:0 zero, value in bits 31:16.
  Write: `exynos_smc(SMC_ID, WRITE_CTRL, value, reg)`.
- Security request (`link_device_shmem.c:2066` `shmem_security_request`):
  `SMC 0x82001011, 0` (SSS clock on) → `SMC 0x82000700, mode, param2, param3` →
  `SMC 0x82001011, 1` (SSS clock off). Modes (`modem_prj.h`): 0 `CP_BOOT_MODE_NORMAL`
  (param2 = boot size, param3 = main size), 1 `CP_BOOT_MODE_DUMP`, 2 `CP_BOOT_RE_INIT`
  (0, 0). Only mode 0's return value is checked.
- With `CONFIG_CP_SECURE_BOOT` the kernel does NOT program CP2AP_MEM_CONFIG /
  ADDR_RNG / MIF_CONFIG1/2 / access windows (`exynos_pmu_cp_init` body is
  `#if !defined(CONFIG_CP_SECURE_BOOT)`), so EL3 must do that.
- `exynos_smc()` (`drivers/soc/samsung/exynos-smc.c`, `arch/arm64/kernel/exynos-smc.S`)
  is a plain `smc #0` with x0–x3 plus optional logging; mainline `arm_smccc_smc` is
  equivalent. No other downstream SMC that registers or initialises the CP service was
  found.

## Downstream CP boot order

libsamsung-ipc `herolte.c` + `modem_ctrl_ss310ap.c`:

1. `IOCTL_MODEM_RESET` — `ss310ap_reset` returns early while `phone_state` is OFFLINE
   (no SMC).
2. `IOCTL_SECURITY_REQ` mode 2 (`CP_BOOT_RE_INIT`, 0, 0).
3. `IOCTL_DPRAM_SEND_BOOT` chunks: BOOT, MAIN (from RADIO), NV (`/efs/nv_data.bin`).
4. `IOCTL_SECURITY_REQ` mode 0 (signature check, sizes of BOOT and MAIN).
5. `IOCTL_MODEM_DL_START` → power on → `exynos_get_cp_power_status()` → first CP_CTRL
   read via SMC.

Downstream never reads CP_CTRL before a verified image exists.

## Test on mainline (2026-10-20)

Probe module `mainline-tools/cpprobe/` (out-of-tree, built with
`make -C linux-7.2.y O=build-mainline ARCH=arm64 LLVM=1 KBUILD_MODPOST_WARN=1 M=...`;
needed `modules_prepare` and `include/generated/utsrelease.h` set to the running
`7.2.11-j4-00048-g662c949bde1e-dirty` — the next `build.sh` regenerates it). Kernel
running: `#107`, root on p18.

| SMC | Result |
|---|---|
| `0x82000700, 3, {0,1}, CP_CTRL_S` | `x0=0xb`, `x1=0x0` (both halves) |
| `0x82000700, 3, {0,1}, CP_CTRL_NS` | `x0=0xb`, `x1=0x0` (both halves) |
| `0x82001011, 0` (SSS clk on) | `0x1` |
| `0x82000700, 2, 0, 0` (`CP_BOOT_RE_INIT`) | `0xb` |
| `0x82001011, 1` (SSS clk off) | `0x0` |
| CP_CTRL reads again after the above | `x0=0xb`, now `x1=0x1` |

Note: the `RE_INIT` call was sent once (the same call downstream issues at every CP
boot, CP off). It returned 0xb; whether it changed any EL3 state is unknown. The phone
stayed up.

## Hypotheses (unverified)

1. **EL3 locks the CP service until mode 0 has verified an image.** Consistent with the
   downstream boot order. Does not obviously explain `RE_INIT` → 0xb, unless downstream
   also gets 0xb there (it ignores that return value, so nobody has looked).
2. **Boot-environment difference** (S-BOOT → uniLoader → mainline vs. the downstream
   boot) makes EL3 reject the whole service. Weak hint: x1 kept the value the SSS call
   left, as if the CP handler returned early without touching registers.

## Next step (not done; needs the user's go-ahead)

Run the same probe on the downstream 3.18 kernel (rebuild for 3.18 in `j4-gcc6`, using
`exynos_smc`):

- after boot with samsungipcd stopped (CP still off), and
- again after samsungipcd has booted the CP.

| Downstream result | Meaning |
|---|---|
| 0xb before CP boot, valid values after | Hypothesis 1 — mainline just needs the full sequence (carveout upload, mode 0, power on) |
| Valid values before CP boot | Hypothesis 2 — find the mainline/uniLoader difference before porting `modem_v1` |

Also check whether the current downstream boot goes through uniLoader
(`boot.img.uniloader-ds`) or straight from S-BOOT; if downstream already works through
uniLoader, uniLoader is not the cause.

## Port plan once unblocked

1. CP power control driver (SMC-based), small.
2. Mailbox driver + DT node (check for a CMU gate first; never read undefined offsets).
3. Port `modem_v1` + `shm_ipc` as staging quality keeping the chardev/ioctl ABI; pdata
   from `modem-ss305ap-pdata.dtsi`.
4. Boot CP with samsungipcd/herolte; confirm `SMS_DEVICE_READY` and the minimal init
   replies (0x0808, 0x0d14) on `umts_ipc0`.
5. `rmnet0` + the existing MM plugin.

Carried-over open issue: SIM works only in slot 2 (not kernel-related).

## Downstream probe (2026-10-23) — decides hypothesis 1

`mainline-tools/cpprobe-ds/` (3.18 build in `j4-gcc6`, inline `smc #0` since
`exynos_smc` is not exported, MODVERSIONS ok). Downstream `#28` booted through uniLoader
(`boot.img.uniloader-ds` in RECOVERY), fresh Debian 11 rootfs on p18 (no samsungipcd
installed, so the CP stays off at boot).

| State | CP_CTRL_S | CP_CTRL_NS |
|---|---|---|
| after boot, CP never booted | `x0=0xb` (both halves) | `x0=0xb` (both halves) |
| after samsungipcd (run from /tmp) booted the CP to ONLINE | `0x00000000` | `0x001006a2` (halves `0x06a20000`, `0x00100000`) |

- Hypothesis 1 confirmed: EL3 refuses CP_CTRL reads until an image has been verified.
  It is the same through uniLoader, so uniLoader is not the cause either.
- The downstream log's two `exynos_smc output` lines are the SSS clock on/off calls
  (0x1, 0x0); the mode 2 (`RE_INIT`) return value is never logged or checked, so the
  mainline `RE_INIT` -> 0xb is not a known difference.
- Downstream mode 0 call: `mode=0, size=5912, addr=34338852` (param2 = BOOT size,
  param3 = MAIN size) -> return 0.

Next: on mainline, put BOOT + MAIN into the carveout exactly where `IOCTL_DPRAM_SEND_BOOT`
puts them and issue mode 0; a 0 return proves EL3 accepts the mainline environment
before `modem_v1` is ported.

## Mode 0 on mainline (2026-10-23) — EL3 accepts the mainline environment

`mainline-tools/cpboot/` on mainline `#110` (eoc4 image): TOC from RADIO (p12) — BOOT
offset 0x200 load 0x40000000 size 0x1718, MAIN offset 0x1920 load 0x40010000 size
0x20bf824, NV load 0x44a00000 size 0x100000 (from `/efs/nv_data.bin`), OFFSET entry not
uploaded. Placed at loadaddr - 0x40000000 in the boot region (carveout 0x73400000,
`ioremap_wc`, region 0x5800000 = `shmem,ipc_offset` of modem-ss305ap-pdata.dtsi; IPC
region +0x5800000 size 0x400000).

| Step | Result |
|---|---|
| CP_CTRL reads before | `0xb` |
| SSS on / mode 2 (RE_INIT) / SSS off | `0x1` / `0xb` / `0x0` |
| copy BOOT+MAIN+NV (35 MB) | ~0.24 s |
| SSS on / mode 0 (0x1718, 0x20bf824) / SSS off | `0x1` / **`0x0`** / `0x0` |
| CP_CTRL reads after | CP_CTRL_S `0x00000000`, CP_CTRL_NS `0x001006a2` (same as downstream with the CP running) |

The signature check passes on mainline, and CP_CTRL becomes readable; CP_CTRL_NS 0x001006a2
is already there before the CP is powered. Mode 2's 0xb is harmless (downstream never
checks it). The CP was not powered on. Next: port the CP power sequence (pmu-cp.c over
SMC), the mailbox and modem_v1.

## CP start on mainline (2026-10-23) — the CP boot loader runs

`cpboot start=1` (second run in the same boot): mode 2 now returns **0** (it returned 0xb
only while no image had been verified yet), mode 0 0 again. CMU_MIF CLK_ENABLE_CLK_MIF_APB
(0x10460814) = 0x3ffffe77, bit 22 MAILBOX_CEL on (left by S-BOOT; mainline's clock driver
does not know the gate). Mailbox `0x10500000` ISSR0-7 all 0 before. Set up like
`init_mailbox_regs()` with this phone's logged values: ISSR2 = 0x800a0 (sys_rev 2 << 6,
ds_det 0, cp_cpu_freq_asv 1 << 19, pda_active bit 5), ISSR5 = 750000, ISSR7 = 818750.
CP_CTRL_NS 0x1006a2 already has CP_PWRON (downstream logs "CP aleady Power on, Just
start!" too), CP_CTRL_S 0 -> 0x8 (CP_START) via SMC WRITE_CTRL (4) -> 0.

ISSR3 = 0x2 (cp_status 1, bits 4:1) within 50 ms — what downstream `ss310ap_boot_on`
reads. INTSR0/1 stayed 0. The CP is left waiting for the boot handshake (0x900d over the
boot link) until the next reboot. Next: mailbox driver + `modem_v1` port so samsungipcd's
herolte path (DL_START, 0x900d/0xa00d, IPC) can run.

## modem_v1 on mainline (2026-10-23) — CP boots, IPC flows

`linux-7.2.y` d51958b0e (driver) + 3e1736be2 (DT): downstream modem_v1 + mcu_ipc + shm_ipc
+ pmu-cp ported as `modem_if.ko` (`make ... M=drivers/misc/modem_v1`, insmod). Same device
set as downstream. samsungipcd (run from /tmp with `/dev/ptmx` as its tty, since the
downstream-only ttygsm driver is missing) boots the CP: both handshake stages pass,
BOOTING -> ONLINE in ~2 s, FMT/RFS IPC flows. First attempt oopsed in shmem_xmit_boot:
mif_pdata needs the board dts `reg = <0 0x10000 0x0>` (MAIN offset, syscp_info).

Left: ttygsm (downstream TTY_GSM_VIRTUAL) for samsungipcd's AT ports, the ModemManager
plugin path, rmnet data, the usim_det SIM-detect pins (gpa1-4/gpa2-4 func 15, separate
downstream driver drivers/misc/usim_det), building it in-tree.

## CP AT on umts_router + rmnet0 data (2026-10-23)

- `/dev/umts_router` (iod id 25, "Data Router") is the CP's own AT parser: AT/ATI/AT+CGMI/
  AT+CGMR (J400FXXS9CVE4)/CPIN/CREG/CEREG/COPS/CSQ/CGDCONT/CGATT/CGACT/CGPADDR all answer
  (probe: perl atprobe.pl, scratch). LTE attach and `AT+CGACT=1,1` work there (address via
  CGPADDR); its `+CGCONTRDP` reply is mangled (`1,5,"internet","76.146.121.70"`, no DNS).
  Ping 1.1.1.1 over rmnet0 with that context: tx only, rx 0 — NOT conclusive (see below).
- Same test with the PDP activated over IPC by samsungipcd (AT on its CUSE port; mainline
  needs fuse.ko + cuse.ko, CONFIG_CUSE=m): ping 1.1.1.1 still 0/3, but a DNS query to the
  carrier DNS 192.168.141.29 over rmnet0 is answered -> **rmnet0 data path works on
  mainline both ways**. The failing ping is probably the SIM having no data quota (user
  suspects so; unverified).
- Open: repeat the AT-activated context test with the carrier DNS query to learn whether an
  AT context is bound to rmnet0.

## Data works with a data plan; CP crash on incoming SMS (2026-10-23)

- With a data plan: samsungipcd (CUSE AT port) `AT+CGACT=1,1` (after LTE registration; the
  first try times out as known) -> 10.20.170.243 on rmnet0 -> ping 1.1.1.1 5/5, avg 52 ms.
  Deactivate + reactivate in one session OK.
- FIXED (samsungipcd, see below). CP crashed (`shmem<-ss305ap: ERR! CP_CRASH_EXIT`) twice, both right after an incoming SMS
  (the carrier's package SMS, `+CMTI`). Second time, from the on-disk log:
  RX 0x0402 IPC_SMS_INCOMING_MSG -> 4 ms later samsungipcd TX 0x0406 IPC_SMS_DELIVER_REPORT
  EXEC `02 00 00 01 ff` (type STATUS_REPORT, ack 0, id 1, `unknown` uninitialised = 0xff;
  libsamsung-ipc's 5-byte layout from older Samsung modems) -> CP 0x0406 reply ->
  CRASH_EXIT 45 ms later. Suspect: that delivery report (inference; needs a test SMS with and
  without the report). A `umts_router` AT+CGACT=0,1 was 2 s earlier, so not ruled out yet.
- The poll spam (47k lines that pushed the crash out of the journal): samsungipcd ignores
  POLLHUP and loops; misc_poll's state messages are now ratelimited.
- After a crash the router AT test stays undecided: router `+CGACT: 1,1` but CGPADDR 0.0.0.0
  right after the IPC side deactivated cid 1.
- Fix verified: the crash came after the SECOND delivery report each time (run 1: different
  SMS, run 2: re-delivered SMS). samsungipcd now echoes the incoming type (01) and zeroes the
  struct: report `01 00 00 01 00`; 5 SMS in a row acked, no crash.
- `umts_router` AT next to samsungipcd is NOT usable as a second master: after samsungipcd
  deactivated cid 1 the router still reported `+CGACT: 1,1` with the old address; router
  `AT+CGACT=0,1` then never answered and the router AT parser stayed dead (no reply to `AT`
  for >60 s), the modem briefly lost registration (+CREG 1,0) and came back, no CP crash.
  Router-only control is not an option either: CP boot, RFS (NV) and SMS need the IPC side.
