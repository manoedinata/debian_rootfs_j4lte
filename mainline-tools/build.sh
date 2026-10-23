#!/bin/bash
#
# Builds the mainline J4 kernel (linux-7.2.y) with LLVM in the j4-mainline
# docker container (debian:trixie: clang, lld, flex, bison, ...), out of tree
# into build-mainline/. The j4-gcc6 container is for the downstream 3.18
# kernel only; mainline needs a modern compiler.
#
# usage: mainline-tools/build.sh [make targets...]   (default: Image + dtb)
#
# LINUX / BUILD pick another tree and output dir, e.g. the 6.12 port for OpenWrt:
#   LINUX=linux-6.12.y BUILD=build-6.12 mainline-tools/build.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="j4-mainline"
JOBS="${JOBS:-$(nproc)}"
LINUX="${LINUX:-linux-7.2.y}"
BUILD="${BUILD:-build-mainline}"

if ! docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
	echo "error: container $CONTAINER_NAME missing (see mainline-tools/README.md)" >&2
	exit 1
fi
docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME" || docker start "$CONTAINER_NAME" >/dev/null

TARGETS="${*:-Image exynos/exynos7570-j4lte.dtb}"

docker exec -u "$(id -u):$(id -g)" -w /work "$CONTAINER_NAME" bash -c "
	set -euo pipefail
	SRC=/work/$LINUX OUT=/work/$BUILD
	M=\"make -C \$SRC O=\$OUT ARCH=arm64 LLVM=1 -j$JOBS\"
	if [ ! -f \$OUT/.config ]; then
		mkdir -p \$OUT
		\$M defconfig
		\$SRC/scripts/kconfig/merge_config.sh -m -O \$OUT \$OUT/.config /work/mainline-tools/j4-mainline.config
		\$M olddefconfig
	fi
	\$M $TARGETS
"
echo "==> Image: $ROOT/$BUILD/arch/arm64/boot/Image"
echo "==> dtb:   $ROOT/$BUILD/arch/arm64/boot/dts/exynos/exynos7570-j4lte.dtb"
