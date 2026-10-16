#!/bin/bash
#
# Builds the j4cam kernel module (V4L2 front-end for the J4's FIMC-IS2 cameras)
# against ./kernel with the same gcc-6 aarch64 toolchain container as
# build_kernel.sh, and installs it into debootstrap-rootfs as a systemd service.
# j4cam replaces the userspace camd daemon (build_camd.sh); do not enable both.
#
#   NO_INSTALL=1 ./build_j4cam.sh    only build; output lands in misc-files/j4cam/
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/j4cam"
UDEV_DIR="$SCRIPT_DIR/camd"	# the udev rules are shared with camd
KERNEL_DIR="$SCRIPT_DIR/kernel"
OUT_DIR="$SCRIPT_DIR/misc-files/j4cam"
ROOTFS_DIR="$SCRIPT_DIR/debootstrap-rootfs"
CONTAINER_NAME="j4-gcc6"

if [ ! -f "$SRC_DIR/j4cam_main.c" ] || [ ! -f "$KERNEL_DIR/Module.symvers" ]; then
	echo "error: need $SRC_DIR/j4cam_main.c and a built kernel ($KERNEL_DIR/Module.symvers) - run build_kernel.sh first" >&2
	exit 1
fi
if ! docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
	echo "error: $CONTAINER_NAME container not found - run build_kernel.sh first to create it" >&2
	exit 1
fi
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
	echo "==> starting $CONTAINER_NAME container"
	docker start "$CONTAINER_NAME" >/dev/null
fi

echo "==> building j4cam.ko against $KERNEL_DIR"
docker exec "$CONTAINER_NAME" rm -rf /tmp/j4cam-build
docker cp "$SRC_DIR" "$CONTAINER_NAME:/tmp/j4cam-build"
docker exec -w /tmp/j4cam-build "$CONTAINER_NAME" bash -c \
	'export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-; make -C /kernel M=/tmp/j4cam-build modules >/dev/null'
mkdir -p "$OUT_DIR"
docker cp "$CONTAINER_NAME:/tmp/j4cam-build/j4cam.ko" "$OUT_DIR/j4cam.ko"
docker exec "$CONTAINER_NAME" rm -rf /tmp/j4cam-build

echo "==> built: $OUT_DIR/j4cam.ko"
if [ "${NO_INSTALL:-}" = 1 ]; then
	exit 0
fi

if [ ! -d "$ROOTFS_DIR" ]; then
	echo "error: missing $ROOTFS_DIR" >&2
	exit 1
fi

echo "==> installing into debootstrap-rootfs"
# debootstrap-rootfs is root-owned (see build_system_img.sh): a sudo prompt
# here is expected unless NOPASSWD sudo is set up.
sudo install -d -m 755 "$ROOTFS_DIR/usr/local/lib/j4cam"
sudo install -o root -g root -m 644 "$OUT_DIR/j4cam.ko" "$ROOTFS_DIR/usr/local/lib/j4cam/j4cam.ko"

sudo install -d -m 755 "$ROOTFS_DIR/etc/systemd/system/multi-user.target.wants"
sudo install -o root -g root -m 644 "$SRC_DIR/j4cam.service" "$ROOTFS_DIR/etc/systemd/system/j4cam.service"
sudo ln -sf /etc/systemd/system/j4cam.service "$ROOTFS_DIR/etc/systemd/system/multi-user.target.wants/j4cam.service"

# j4cam supersedes the userspace camd bridge
for unit in camd-loopback camd-rear camd-front camd; do
	sudo rm -f "$ROOTFS_DIR/etc/systemd/system/multi-user.target.wants/$unit.service" \
		   "$ROOTFS_DIR/etc/systemd/system/$unit.service"
done

# FIMC-IS2 looks its firmware up under the stock Android path.
sudo install -d -m 755 "$ROOTFS_DIR/system/vendor"
sudo ln -sfn /vendor/firmware "$ROOTFS_DIR/system/vendor/firmware"

# udev: v4l_id must skip the FIMC-IS nodes (it crashes the driver), and they get
# parked in /dev/camd/ where j4cam opens them.
sudo install -d -m 755 "$ROOTFS_DIR/etc/udev/rules.d"
sudo install -o root -g root -m 644 "$UDEV_DIR/60-persistent-v4l.rules" "$ROOTFS_DIR/etc/udev/rules.d/60-persistent-v4l.rules"
sudo install -o root -g root -m 644 "$UDEV_DIR/61-hide-fimc-is.rules" "$ROOTFS_DIR/etc/udev/rules.d/61-hide-fimc-is.rules"

echo "==> done"
