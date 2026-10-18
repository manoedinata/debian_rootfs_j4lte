#!/bin/bash
#
# Packs the mainline Image + dtb (from mainline-tools/build.sh) into a flashable
# boot.img: uniLoader (embedding Image, dtb and the initramfs) as the boot.img
# "kernel", header parameters copied from the AIK split of the stock image.
#
# uniLoader is built in a throwaway copy (build-uniloader/) so uniLoader/blob
# keeps whatever the downstream image was built from. Nothing is flashed here.
#
# usage: mainline-tools/pack.sh [output.img]   (default: build-mainline/boot-mainline.img)
#
# RAMDISK defaults to a cpio of initramfs/. IMAGE / DTB / RAMDISK override the embedded payload, e.g. to test uniLoader
# itself with the downstream kernel:
#   IMAGE=<downstream Image> DTB=<j4lte dtb> RAMDISK=<ramdisk.gz> PAYLOAD_ENTRY=0x40080000 \
#       mainline-tools/pack.sh boot.img.uniloader-ds
#
# BOOTARGS_EXTRA is appended to /chosen/bootargs of the embedded dtb copy. uniLoader
# hands the kernel the raw dtb, so args S-BOOT normally adds are missing; the
# downstream display driver needs lcdtype= (0 means "no LCD": panel never relit).
#
# BOOTARGS_REMOVE: space-separated tokens dropped from /chosen/bootargs first (e.g.
# console=ttySAC2,115200: with no UART attached it only slows the boot).
#
# PAYLOAD_ENTRY is where uniLoader copies the Image and jumps (default: the
# j4lte_defconfig value, 0x50000000). Downstream 3.18 derives PHYS_OFFSET from
# its load address (head.S: adrp x24, __PHYS_OFFSET = _text - TEXT_OFFSET), so it
# must sit at RAM base + 0x80000 = 0x40080000 where S-BOOT puts it; mainline
# takes any 2 MiB-aligned address.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/build-mainline"
UL="$ROOT/build-uniloader"
SPLIT="$ROOT/AIK-Linux-mirror/split_img"
MKBOOTIMG="$ROOT/AIK-Linux-mirror/bin/linux/x86_64/mkbootimg"
OUT="${1:-$BUILD/boot-mainline.img}"
RAMDISK="${RAMDISK:-}"
CONTAINER_NAME="j4-mainline"

IMAGE="${IMAGE:-$BUILD/arch/arm64/boot/Image}"
DTB="${DTB:-$BUILD/arch/arm64/boot/dts/exynos/exynos7570-j4lte.dtb}"
if [ -z "$RAMDISK" ]; then
	# default: the repo's initramfs/ (root=/dev/mmcblk0p18), same recipe as AIK repack
	RAMDISK="$ROOT/build-uniloader-ramdisk.gz"
	(cd "$ROOT/initramfs" && find . ! -name . | LC_ALL=C sort | cpio -o -H newc -R 0:0 --quiet | gzip -9n > "$RAMDISK")
fi
for f in "$IMAGE" "$DTB" "$RAMDISK" "$MKBOOTIMG"; do
	[ -f "$f" ] || { echo "error: missing $f" >&2; exit 1; }
done
docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME" || docker start "$CONTAINER_NAME" >/dev/null

echo "==> staging uniLoader copy in $UL"
mkdir -p "$UL"
rsync -a --delete --exclude .git --exclude blob --exclude '*.o' --exclude '*.a' \
	--exclude uniLoader --exclude 'uniLoader.*' --exclude .config "$ROOT/uniLoader/" "$UL/"
mkdir -p "$UL/blob"
cp -f "$IMAGE" "$UL/blob/Image"
cp -f "$DTB" "$UL/blob/dtb"
cp -f "$RAMDISK" "$UL/blob/ramdisk"

if [ -n "${BOOTARGS_EXTRA:-}${BOOTARGS_REMOVE:-}" ]; then
	docker exec -u "$(id -u):$(id -g)" "$CONTAINER_NAME" bash -c '
		set -euo pipefail
		dtb=/work/build-uniloader/blob/dtb
		old=$(fdtget -t s "$dtb" /chosen bootargs 2>/dev/null || true)
		for tok in $2; do old=$(printf " %s " "$old" | sed "s| $tok | |g"); done
		new=$(echo "$old $1" | xargs)
		fdtput -t s "$dtb" /chosen bootargs "$new"
		echo "==> dtb bootargs: $(fdtget -t s "$dtb" /chosen bootargs)"
	' _ "${BOOTARGS_EXTRA:-}" "${BOOTARGS_REMOVE:-}"
fi

# J4 hand-off variant (state report, copy verify, cache maintenance)
cp -f "$ROOT/mainline-tools/uniloader/load-kernel.c" "$UL/arch/aarch64/load-kernel.c"

if [ -n "${PAYLOAD_ENTRY:-}" ]; then
	sed -i "s/^CONFIG_PAYLOAD_ENTRY=.*/CONFIG_PAYLOAD_ENTRY=$PAYLOAD_ENTRY/" "$UL/configs/j4lte_defconfig"
fi

echo "==> building uniLoader (j4lte)"
docker exec -u "$(id -u):$(id -g)" -w /work/build-uniloader "$CONTAINER_NAME" bash -c '
	set -euo pipefail
	make ARCH=aarch64 LLVM=1 j4lte_defconfig
	make ARCH=aarch64 LLVM=1 -j"$(nproc)"
	grep -E "^CONFIG_(TEXT_BASE|PAYLOAD_ENTRY|RAMDISK_ENTRY)" .config
'

echo "==> mkbootimg -> $OUT"
rd=$(mktemp); cp "$RAMDISK" "$rd"
# --dt: the stock DTB table is what S-BOOT parses (board/rev selection); the
# mainline dtb travels inside uniLoader, which ignores this one.
"$MKBOOTIMG" --kernel "$UL/uniLoader" --ramdisk "$rd" --dt "$SPLIT/boot_stock.img-dt" \
	--cmdline "$(cat "$SPLIT/boot_stock.img-cmdline")" \
	--board "$(cat "$SPLIT/boot_stock.img-board")" \
	--base "$(cat "$SPLIT/boot_stock.img-base")" \
	--pagesize "$(cat "$SPLIT/boot_stock.img-pagesize")" \
	--kernel_offset "$(cat "$SPLIT/boot_stock.img-kernel_offset")" \
	--ramdisk_offset 0x02000000 \
	--tags_offset "$(cat "$SPLIT/boot_stock.img-tags_offset")" \
	--os_version "$(cat "$SPLIT/boot_stock.img-os_version")" \
	--os_patch_level "$(cat "$SPLIT/boot_stock.img-os_patch_level")" \
	-o "$OUT"
rm -f "$rd"
# Samsung bootloader wants the SEANDROIDENFORCE trailer
printf 'SEANDROIDENFORCE' >> "$OUT"
ls -l "$OUT"
echo "==> partition limit is 33554432 bytes"
