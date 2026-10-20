# TODO — mainline (linux-7.2.y) on the Galaxy J4 (Exynos7570)

Status as of 2026-10-20.

## Missing drivers

| Area | Status | Notes |
|---|---|---|
| GPU (Mali-T720) | **done** (2026-10-20) | Panfrost at a fixed 349 MHz. Phosh starts at boot and renders on it (verified after reboot, no llvmpipe); wlroots finds the display (card1) by itself. Left: OPP/devfreq on the shared BUCK1 rail (higher clocks), thermal. |
| WiFi / Bluetooth (Samsung SCSC) | missing | No mainline driver; downstream uses the vendor SCSC stack. Port or new driver — big job. |
| Modem / mobile data (Shannon) | missing | Needs the Samsung modem interface + shared-memory link driver. samsungipcd and the MM plugin would then work on top. |
| Audio (cod9002x codec, audmixer, I2S) | missing | No mainline codec or machine driver. Speaker works on downstream. |
| Cameras (FIMC-IS2, S5K3L2 / S5K5E3) | missing | Very large; downstream only works with the vendor stack. |
| CPU frequency scaling / thermal | missing | CPUs run at whatever S-BOOT set, no DVFS. |
| Suspend | not working | `rtcwake` suspend failed; s2idle untried. |
| TC305K touch keys | not ported | |
| Sensors, vibrator, NFC, LED/flash | not looked at | |
| SD card (mmc2) | disabled in DT | Controller driver exists; enable and test. |
| Video codec / scaler / JPEG | not done | |

## Working but incomplete

- Charger: works; end-of-charge and wireless-charging logic missing.
- USB: device mode only (RNDIS/SSH); no host/OTG boost.
- Display: works (DECON is card0/fb0, brightness OK). Still to test:
  - blanking/idle past ~157 s (the SysMMU-suspend SError fix is untested under idle);
  - cold start without the bootloader's picture.
- Fuel gauge cycle counter: untested across full power-off and a real discharge.

## Open bugs

- **Large `apt-get install` runs corrupt data on mainline** (biggest). Cause unknown;
  suspects: HS400 under writeback, DMA cache coherency, reserved-memory overlap with
  the secure world, CPU frequency/voltage left by S-BOOT.

## Already working

4 CPU cores, clocks, pinctrl, PMIC (regulators, RTC, power key, charger, fuel gauge),
eMMC incl. HS400, USB networking + SSH, touchscreen, display with brightness, ramoops,
GPU (Panfrost), Phosh with hardware rendering (enabled at boot, phoc scale-to-fit on).

## Suggested next steps

1. Audio.
2. WiFi.
3. GPU follow-ups: OPP/devfreq, thermal.
