# TODO — mainline on the Galaxy J4 (Exynos7570)

Status as of 2026-11-24. Main tree: `linux-6.12.y` (branch `exynos7570-6.12`), used by the
stowaway Debian kernel (RECOVERY) and OpenWrt. `linux-7.2.y` lags behind (see below).

## Done on 6.12 (verified on the phone)

4 CPU cores, clocks, pinctrl, PMIC (regulators, RTC, power key, charger, fuel gauge),
eMMC incl. HS400, USB networking + SSH, touchscreen, DSI display, ramoops, GPU (Panfrost),
modem + mobile data, WiFi (SCSC: STA, AP, repeater), Bluetooth (SCSC + BlueZ, up at boot),
CPU DVFS 344.5-1430 MHz (+1586/1690 opt-in), TMU + CPU thermal zone, volume/home keys,
TC305K recent/back touch keys, vibrator (regulator-haptic), accelerometer (LIS2DS12 with
interrupt, mount matrix), front flash LED (KTD2692), rear flash LED (S2MPU06 flash block:
torch 20-160 mA, 600 mA flash), proximity sensor (GP2AP070S, IIO with near/far events), cpuidle core power-down (PSCI +
PMU lpm_init CPU settings, MCT as per-CPU wakeup timer), ECT and firmware RAM reserved.
Kernel configs tracked in `mainline-tools/configs/`.

## Easy

- [ ] SD card slot (mmc2): enable, 2.8 V supply on gpa0-3, card detect. Needs a card to test.

## Medium

- [ ] Auto-rotate and proximity in Phosh: install iio-sensor-proxy (kernel side done).

## Untested

- [ ] Boot-test the 30 s Bluetooth firmware-wait build (`recovery-stowaway-bt6.img`,
      flashed, not booted yet).
- [ ] Bluetooth real use: pairing, A2DP headset (needs PipeWire/PulseAudio), file transfer,
      a BLE device. Check whether "hci0: unexpected event for opcode 0x0000" at power-on
      also happens downstream.
- [ ] Charger end-of-charge: implemented, never run through a real full charge.
- [ ] Fuel gauge cycle counter: untested across full power-off and a real discharge.
- [ ] 7.2: rebuild with the 0x7e700000 reservation and re-test big `apt` runs (the data
      corruption bug is probably that reservation — not re-tested).

## Porting / packaging / upstream

- [ ] OpenWrt: refresh `patches-6.12` and `config-6.12` with the 2026-11-23 commits and
      options (I2C_GPIO, KEYBOARD_TM2_TOUCHKEY, INPUT_REGULATOR_HAPTIC,
      IIO_ST_ACCEL_I2C_3AXIS, LEDS_KTD2692, LEDS_S2MPU06, GP2AP070S, BT + SCSC_BT_BLUEZ); BlueZ packages for BT.
- [ ] Port the 2026-11-23/24 work to `linux-7.2.y` (keys, touch keys, vibrator, accelerometer,
      flash LEDs, proximity, ECT, Bluetooth), plus 6.12-only WiFi, CPU DVFS and TMU.
- [ ] Send upstream: st_accel LIS2DS12 axis-enable fix, st_accel LIS2DS12 ODR table fix,
      ktd2692 writes with interrupts off.

## Hard

- [ ] Suspend (`rtcwake` suspend failed; s2idle untried). Needs the downstream SYS_SLEEP PMU
      sequences, wakeup masks and driver suspend/resume (DECON/DSIM, SCSC, modem, USB).
- [ ] Idle heat: core power-down works (~99 % of idle) but the thermal zone stayed ~48 C
      (was 49 C; measured while charging over USB, cpufreq at 1.1-1.3 GHz). Look at idle
      cpufreq, BUCK1 floor 825 mV, SICD (downstream system idle).
- [ ] Audio: cod9002x codec, audmixer, I2S, pl330 (speaker works on downstream).
- [ ] Cameras: FIMC-IS2, S5K3L2 / S5K5E3 (work on downstream only via the j4cam path).
- [ ] Display: brightness/blank via DRM, idle blanking, cold start without the
      bootloader's picture.
- [ ] GPU OPPs/devfreq (fixed 349 MHz), MIF/INT DVFS.
- [ ] USB host/OTG with charge boost; jig/UART cables.
- [ ] NFC: unknown whether the J400F has the chip (downstream DT lists pn547 and sec-nfc).
- [ ] Video codec / scaler / JPEG.

## Other

- uniLoader gzip kernel (`KERNEL_GZIP=1`): boots, but inflating is very slow with the MMU
  off (every access uncached, byte-by-byte decoder). Fix: identity-map DRAM as Normal
  cacheable before inflating, clean/invalidate and turn the MMU off before the jump.
- LTE band selection/locking (asked 2026-10-25): luci-app-modemband cannot work (needs
  vendor AT commands, conflicts with ModemManager). Plan: decode the band-selection IPC
  message from libsec-ril, add an AT command to samsungipcd, then a small LuCI page.
