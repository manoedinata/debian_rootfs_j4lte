#!/bin/bash
#
# Restores a known-good Debian BOOT image from TWRP (phone in recovery, adb up).
# Needed after a mainline test image that leaves the phone without SSH.
#
# usage: mainline-tools/restore-debian-boot.sh [image]   (default: boot.img.uniloader-ds)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:-$ROOT/boot.img.uniloader-ds}"
BOOT_DEV=/dev/block/mmcblk0p10   # BOOT, 32 MiB

[ -f "$IMG" ] || { echo "error: $IMG not found" >&2; exit 1; }
adb get-state | grep -qx recovery || { echo "error: phone is not in TWRP (adb state: $(adb get-state))" >&2; exit 1; }
[ "$(adb shell "blockdev --getsize64 $BOOT_DEV" | tr -d '\r')" = 33554432 ] || { echo "error: $BOOT_DEV is not the 32 MiB BOOT partition" >&2; exit 1; }

size=$(stat -c %s "$IMG")
want=$(sha256sum "$IMG" | cut -c1-64)
echo "==> writing $IMG ($size bytes) to $BOOT_DEV"
adb shell -e none -T "dd of=$BOOT_DEV bs=1048576 conv=fsync 2>/dev/null; sync" < "$IMG"
got=$(adb exec-out "dd if=$BOOT_DEV bs=1048576 2>/dev/null | head -c $size" | sha256sum | cut -c1-64)
[ "$got" = "$want" ] && echo "==> readback matches ($want)" || { echo "READBACK MISMATCH: $got" >&2; exit 1; }
echo "==> now: adb reboot"
