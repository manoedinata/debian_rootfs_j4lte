#!/bin/bash
#
# Turns a fresh debootstrap of Debian 11 (rootfs-bullseye/, arm64, minbase +
# ssh/NM/systemd) into a bootable J4 SYSTEM rootfs: hostname, apt sources,
# fstab (root on SYSTEM, VENDOR/EFS read-only), volatile journald, the RNDIS
# DHCP server (unudhcpd) and a sudo user. Runs as root on the host; the chroot
# steps go through qemu-aarch64 binfmt. Pack with
#   ROOTFS_DIR=rootfs-bullseye OUT_IMG=system-bullseye.img JOURNAL=1 ./build_system_img.sh
#
# Login: ssh nata@172.16.42.1 (password from USER_PASSWORD, sudo). No root key
# is installed: add yours after the first boot (ssh-copy-id).
#   sudo USER_PASSWORD=... ./setup_rootfs_bullseye.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="${ROOTFS_DIR:-$SCRIPT_DIR/rootfs-bullseye}"
[ "$(id -u)" = 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
[ -x "$R/bin/bash" ] || { echo "error: $R is not a debootstrapped rootfs" >&2; exit 1; }
[ -n "${USER_PASSWORD:-}" ] || { echo "error: set USER_PASSWORD for user nata" >&2; exit 1; }

echo galaxy-j4 >"$R/etc/hostname"
cat >"$R/etc/hosts" <<'EOF'
127.0.0.1	localhost
127.0.1.1	galaxy-j4
::1		localhost ip6-localhost ip6-loopback
EOF

cat >"$R/etc/apt/sources.list" <<'EOF'
deb http://archive.debian.org/debian bullseye main contrib non-free
deb http://archive.debian.org/debian-security bullseye-security main contrib non-free
EOF

# The initramfs mounts root rw and /vendor itself; systemd adopts both.
# USERDATA (mmcblk0p25) is the laptop's USB disk: never mount it here.
mkdir -p "$R/vendor" "$R/efs"
cat >"$R/etc/fstab" <<'EOF'
# <file system>  <mount point>  <type>  <options>              <dump>  <pass>
/dev/mmcblk0p18  /              ext4    defaults,noatime,errors=remount-ro  0  1
# Stock VENDOR (firmware blobs), read-only
/dev/mmcblk0p19  /vendor        ext4    ro,nofail              0       2
# Stock EFS (modem NV data, IMEI): irreplaceable, keep it READ-ONLY
/dev/mmcblk0p3   /efs           ext4    ro,nofail              0       2
EOF

mkdir -p "$R/etc/systemd/journald.conf.d"
cat >"$R/etc/systemd/journald.conf.d/volatile.conf" <<'EOF'
[Journal]
Storage=volatile
EOF

# USB tether: the initramfs creates rndis0, unudhcpd hands the host 172.16.42.2
install -m 0755 "$SCRIPT_DIR/misc-files/unudhcpd" "$R/usr/local/sbin/unudhcpd"
cat >"$R/etc/systemd/system/unudhcpd.service" <<'EOF'
[Unit]
Description=unudhcpd DHCP server for the USB (rndis0) tether interface
# rndis0 comes and goes with the USB cable (gadget set up by the initramfs)
BindsTo=sys-subsystem-net-devices-rndis0.device
After=sys-subsystem-net-devices-rndis0.device

[Service]
ExecStartPre=/sbin/ip addr replace 172.16.42.1/24 dev rndis0
ExecStartPre=/sbin/ip link set rndis0 up
ExecStart=/usr/local/sbin/unudhcpd -i rndis0 -s 172.16.42.1 -c 172.16.42.2
Restart=on-failure
RestartSec=1

[Install]
WantedBy=sys-subsystem-net-devices-rndis0.device
EOF
mkdir -p "$R/etc/systemd/system/sys-subsystem-net-devices-rndis0.device.wants"
ln -sf /etc/systemd/system/unudhcpd.service \
	"$R/etc/systemd/system/sys-subsystem-net-devices-rndis0.device.wants/unudhcpd.service"

mkdir -p "$R/etc/NetworkManager/conf.d"
cat >"$R/etc/NetworkManager/conf.d/10-unmanaged-rndis0.conf" <<'EOF'
[keyfile]
unmanaged-devices=interface-name:rndis0
EOF

ln -sf /usr/share/zoneinfo/Asia/Jakarta "$R/etc/localtime"
echo Asia/Jakarta >"$R/etc/timezone"
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' "$R/etc/locale.gen"

chroot "$R" /bin/bash -euc '
	locale-gen >/dev/null
	update-locale LANG=en_US.UTF-8
	id nata >/dev/null 2>&1 || useradd -m -u 1000 -s /bin/bash nata
	for grp in video input audio render netdev plugdev; do getent group $grp >/dev/null || groupadd -r $grp; done
	usermod -aG sudo,video,input,audio,render,netdev,plugdev nata
	systemctl enable ssh systemd-timesyncd NetworkManager >/dev/null 2>&1
	apt-get clean
'
echo "nata:$USER_PASSWORD" | chroot "$R" chpasswd
rm -rf "$R/var/lib/apt/lists/"*
echo "==> $R configured"
