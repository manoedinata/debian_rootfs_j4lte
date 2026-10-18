#!/bin/bash
#
# Puts the TWRP backup back into the RECOVERY partition (mmcblk0p11) from a
# running Debian over SSH. Use it to end the "mainline test image lives in
# RECOVERY" workflow.
#
# usage: mainline-tools/restore-twrp.sh [image]   (default: recovery.img.twrp-backup)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:-$ROOT/recovery.img.twrp-backup}"
HOST="${HOST:-root@172.16.42.1}"
SSH=(ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST")
DEV=/dev/mmcblk0p11   # RECOVERY, 39845888 bytes

[ -f "$IMG" ] || { echo "error: $IMG not found" >&2; exit 1; }
size=$(stat -c %s "$IMG")
want=$(sha256sum "$IMG" | cut -c1-64)
[ "$("${SSH[@]}" "blockdev --getsize64 $DEV" 2>/dev/null)" = 39845888 ] || { echo "error: $DEV is not the 39845888-byte RECOVERY partition" >&2; exit 1; }

scp -q -o BatchMode=yes "$IMG" "$HOST:/tmp/recovery-new.img"
got=$("${SSH[@]}" "sha256sum /tmp/recovery-new.img | cut -c1-64" 2>/dev/null)
[ "$got" = "$want" ] || { echo "transfer mismatch" >&2; exit 1; }
rb=$("${SSH[@]}" "dd if=/tmp/recovery-new.img of=$DEV bs=1M conv=fsync 2>/dev/null; sync; dd if=$DEV bs=1M 2>/dev/null | head -c $size | sha256sum | cut -c1-64" 2>/dev/null)
[ "$rb" = "$want" ] && echo "==> RECOVERY restored from $IMG (readback $want)" || { echo "READBACK MISMATCH $rb" >&2; exit 1; }
