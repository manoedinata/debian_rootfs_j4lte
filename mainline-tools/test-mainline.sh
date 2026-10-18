#!/bin/bash
#
# Mainline test loop with the test image living in RECOVERY (BOOT stays the
# working Debian image).
#
#   test-mainline.sh flash     write build-mainline/boot-mainline.img to RECOVERY (verified)
#   test-mainline.sh reboot    'reboot recovery' on the phone -> boots the mainline image,
#                              which reboots itself (j4.autoreboot) back into Debian
#   test-mainline.sh dump      wait for Debian, dump + decode the ramoops console
#   test-mainline.sh run       flash, reboot, dump
#
# The decoded log is printed and saved to mainline-tools/logs/<timestamp>-console.txt.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-root@172.16.42.1}"
IMG="${IMG:-$ROOT/build-mainline/boot-mainline.img}"
SSH=(ssh -o ConnectTimeout=8 -o BatchMode=yes "$HOST")
DEV=/dev/mmcblk0p11   # RECOVERY, 39845888 bytes
RAMOOPS_ADDR=0x7e100000
RAMOOPS_SIZE=0x180000
ssh_q() { "${SSH[@]}" "$@" 2> >(grep -v 'post-quantum\|store now\|openssh.com/pq' >&2); }

wait_for_debian() {
	local max=${1:-240} i u
	sleep 15
	for ((i = 0; i < max / 4; i++)); do
		u=$("${SSH[@]}" 'cut -d. -f1 /proc/uptime' 2>/dev/null) && [ -n "$u" ] && { echo "$u"; return 0; }
		sleep 4
	done
	return 1
}

do_flash() {
	[ -f "$IMG" ] || { echo "error: $IMG not found" >&2; exit 1; }
	local size want got rb
	size=$(stat -c %s "$IMG"); want=$(sha256sum "$IMG" | cut -c1-64)
	[ "$size" -le 39845888 ] || { echo "error: image larger than the RECOVERY partition" >&2; exit 1; }
	[ "$(ssh_q "blockdev --getsize64 $DEV")" = 39845888 ] || { echo "error: $DEV is not the RECOVERY partition" >&2; exit 1; }
	scp -q -o BatchMode=yes "$IMG" "$HOST:/tmp/mainline-test.img"
	got=$(ssh_q "sha256sum /tmp/mainline-test.img | cut -c1-64")
	[ "$got" = "$want" ] || { echo "transfer mismatch" >&2; exit 1; }
	rb=$(ssh_q "dd if=/tmp/mainline-test.img of=$DEV bs=1M conv=fsync 2>/dev/null; sync; dd if=$DEV bs=1M 2>/dev/null | head -c $size | sha256sum | cut -c1-64")
	[ "$rb" = "$want" ] && echo "==> RECOVERY now holds $(basename "$IMG") ($want)" || { echo "READBACK MISMATCH $rb" >&2; exit 1; }
}

do_reboot() {
	echo "==> reboot recovery (mainline boots, runs ~1 min, then reboots into Debian)"
	ssh_q 'sync; (sleep 1; reboot recovery) >/dev/null 2>&1 &' || true
}

do_dump() {
	local up out log
	echo "==> waiting for Debian..."
	up=$(wait_for_debian) || { echo "Debian did not come back (stuck in mainline? use the recovery key combo / power-cycle)" >&2; exit 1; }
	echo "==> Debian up, uptime ${up}s"
	scp -q -o BatchMode=yes "$ROOT/mainline-tools/ramretain/ramretain.ko" "$HOST:/root/" 2>/dev/null
	out=$(mktemp); log="$ROOT/mainline-tools/logs/$(date +%Y%m%d-%H%M%S)-console.txt"
	mkdir -p "$ROOT/mainline-tools/logs"
	ssh_q "mountpoint -q /sys/kernel/debug || mount -t debugfs none /sys/kernel/debug; rmmod ramretain 2>/dev/null; insmod /root/ramretain.ko addr=$RAMOOPS_ADDR size=$RAMOOPS_SIZE mode=dump && cat /sys/kernel/debug/ramretain; rmmod ramretain" > "$out"
	cp "$out" "${log%.txt}.bin"
	python3 "$ROOT/mainline-tools/ramoops_parse.py" "$out" > "$log"
	rm -f "$out"
	echo "==> console saved: $log ($(wc -c < "$log") bytes)"
	cat "$log"
}

case "${1:-}" in
	flash)  do_flash ;;
	reboot) do_reboot ;;
	dump)   do_dump ;;
	run)    do_flash; do_reboot; do_dump ;;
	*) sed -n '2,17p' "$0"; exit 1 ;;
esac
