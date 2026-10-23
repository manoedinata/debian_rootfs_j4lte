#!/bin/bash
#
# Mainline test loop with the test image living in RECOVERY (BOOT stays the
# working Debian image).
#
#   test-mainline.sh flash     write build-mainline/boot-mainline.img to the test slot, BOOT (verified)
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
# The test image lives in BOOT (p10, 33554432 bytes) and downstream Debian in
# RECOVERY, so a hung test boot is one key combo away from Debian. SLOT=recovery
# restores the old layout (test image in RECOVERY p11, 39845888 bytes).
SLOT="${SLOT:-boot}"
if [ "$SLOT" = recovery ]; then
	DEV=/dev/mmcblk0p11; DEVSIZE=39845888; REBOOT_CMD='reboot recovery'
else
	DEV=/dev/mmcblk0p10; DEVSIZE=33554432; REBOOT_CMD='reboot'
fi
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
	[ "$size" -le "$DEVSIZE" ] || { echo "error: image larger than the $SLOT partition" >&2; exit 1; }
	# sysfs size (512-byte sectors): OpenWrt has no blockdev
	[ "$(ssh_q "echo \$((\$(cat /sys/class/block/${DEV#/dev/}/size) * 512))")" = "$DEVSIZE" ] || { echo "error: $DEV is not the $SLOT partition" >&2; exit 1; }
	# plain ssh, not scp: OpenWrt has no sftp-server
	ssh_q "cat > /tmp/mainline-test.img" < "$IMG"
	got=$(ssh_q "sha256sum /tmp/mainline-test.img | cut -c1-64")
	[ "$got" = "$want" ] || { echo "transfer mismatch" >&2; exit 1; }
	rb=$(ssh_q "dd if=/tmp/mainline-test.img of=$DEV bs=1M conv=fsync 2>/dev/null; sync; dd if=$DEV bs=1M 2>/dev/null | head -c $size | sha256sum | cut -c1-64")
	[ "$rb" = "$want" ] && echo "==> $SLOT now holds $(basename "$IMG") ($want)" || { echo "READBACK MISMATCH $rb" >&2; exit 1; }
}

do_reboot() {
	echo "==> $REBOOT_CMD ($SLOT slot boots the mainline test image)"
	ssh_q "sync; (sleep 1; $REBOOT_CMD) >/dev/null 2>&1 &" || true
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
