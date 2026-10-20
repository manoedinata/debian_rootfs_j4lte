#!/bin/sh
#
# Runs on the phone. Emulates the workload that corrupted the root filesystem
# during a big apt run: download (USB network), decompress, many buffered
# writes, and re-reads, comparing everything against known checksums.
#
#   emmc-stress.sh [rounds]     (needs the phone's internet, see phone-internet.sh)
#
N=${1:-6}
W=/var/tmp/stress.$$
mkdir -p $W && cd $W || exit 1
PKGS="libllvm11 libwebkit2gtk-4.0-37 libjavascriptcoregtk-4.0-18"
bad=0

for p in $PKGS; do
	apt-get download $p >/dev/null 2>&1 || { echo "download of $p failed"; exit 1; }
done
ls -l *.deb | awk '{print $5, $9}'
for f in *.deb; do
	p=${f%%_*}
	want=$(apt-cache show $p 2>/dev/null | awk '/^SHA256:/ {print $2; exit}')
	got=$(sha256sum $f | cut -d' ' -f1)
	[ "$want" = "$got" ] || { echo "reference sha of $f does not match the index ($got)"; bad=$((bad+1)); }
	echo "$got  $f" >> ref.sums
done

for i in $(seq 1 $N); do
	# decompress and write each package twice, compare the trees, then the .debs
	for f in *.deb; do
		rm -rf x1 x2
		dpkg-deb -x $f x1 || { echo "round $i: dpkg-deb -x $f failed"; bad=$((bad+1)); }
		dpkg-deb -x $f x2 || { echo "round $i: dpkg-deb -x $f (2) failed"; bad=$((bad+1)); }
		sync
		echo 3 > /proc/sys/vm/drop_caches
		if ! diff -r x1 x2 >/dev/null 2>&1; then
			echo "round $i: $f extracted trees differ:"; diff -rq x1 x2 | head -3
			bad=$((bad+1))
		fi
	done
	echo 3 > /proc/sys/vm/drop_caches
	sha256sum -c ref.sums >/dev/null 2>&1 || { echo "round $i: stored .deb checksums changed"; bad=$((bad+1)); }
	# download again over the network and compare with the stored copy
	for p in $PKGS; do
		rm -f again_$p.deb
		(mkdir -p dl && cd dl && apt-get download $p >/dev/null 2>&1)
	done
	for f in dl/*.deb; do
		cmp -s $f $(basename $f) || { echo "round $i: re-download of $f differs"; bad=$((bad+1)); }
	done
	rm -rf dl
	echo "round $i done, errors so far: $bad"
done
rm -rf $W
echo "RESULT bad=$bad rounds=$N"
