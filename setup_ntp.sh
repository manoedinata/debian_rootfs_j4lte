#!/bin/bash
#
# Sets the system timezone to Asia/Jakarta and installs
# systemd-timesyncd as the NTP client, so the clock auto-syncs on
# boot once networking is up. Debian's systemd package does not pull
# in systemd-timesyncd by default (it's a separate binary package),
# and this debootstrap base has neither it nor any other NTP client
# installed.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOTFS_DIR="$SCRIPT_DIR/debootstrap-rootfs"

if [ ! -d "$ROOTFS_DIR" ]; then
	echo "error: missing $ROOTFS_DIR" >&2
	exit 1
fi

echo "==> setting timezone to Asia/Jakarta"
sudo ln -sf /usr/share/zoneinfo/Asia/Jakarta "$ROOTFS_DIR/etc/localtime"
echo "Asia/Jakarta" | sudo tee "$ROOTFS_DIR/etc/timezone" >/dev/null

echo "==> installing systemd-timesyncd"
sudo mount --bind /dev "$ROOTFS_DIR/dev"
sudo mount -t proc proc "$ROOTFS_DIR/proc"
sudo mount -t sysfs sysfs "$ROOTFS_DIR/sys"
sudo chroot "$ROOTFS_DIR" env DEBIAN_FRONTEND=noninteractive apt-get install -y systemd-timesyncd
sudo umount "$ROOTFS_DIR/dev" "$ROOTFS_DIR/proc" "$ROOTFS_DIR/sys"

echo "==> pointing timesyncd at the Indonesian NTP pool"
sudo install -d -m 755 "$ROOTFS_DIR/etc/systemd/timesyncd.conf.d"
sudo tee "$ROOTFS_DIR/etc/systemd/timesyncd.conf.d/id-pool.conf" >/dev/null <<'EOF'
[Time]
NTP=0.id.pool.ntp.org 1.id.pool.ntp.org 2.id.pool.ntp.org 3.id.pool.ntp.org
EOF

echo "==> enabling systemd-timesyncd.service"
sudo install -d -m 755 "$ROOTFS_DIR/etc/systemd/system/sysinit.target.wants"
sudo ln -sf /lib/systemd/system/systemd-timesyncd.service "$ROOTFS_DIR/etc/systemd/system/sysinit.target.wants/systemd-timesyncd.service"

echo "==> done"
