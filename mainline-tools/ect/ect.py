#!/usr/bin/env python3
"""Decode Samsung's ECT ("PARA") tables from an S-BOOT image.

S-BOOT carries the ECT that it hands to the kernel. On the J4 it sits in
the eMMC boot area; pull it read-only and decode the CPU tables:

    ssh root@172.16.42.1 'cat /dev/mmcblk0boot0' > boot0.bin
    python3 -I ect.py boot0.bin

Prints the DVFS domains (with the dvfs_cpucl0 levels: rate, enabled flag and
the per-level clock values) and the CPUCL0_PLL P/M/S table. Layout follows
the downstream drivers/soc/samsung/ect_parser.c (4-byte aligned strings).
"""
import struct
import sys

d = open(sys.argv[1], 'rb').read()


def u32(o):
    return struct.unpack_from('<I', d, o)[0]


def i32(o):
    return struct.unpack_from('<i', d, o)[0]


def pstr(o):
    n = u32(o) + 1
    s = d[o + 4:o + 4 + n - 1].decode('latin1')
    return s, o + 4 + (n if n % 4 == 0 else n + 4 - n % 4)


def headers(base):
    """block name -> offset, or None if this is no ECT header"""
    nh, tot = i32(base + 12), u32(base + 8)
    if not (0 < nh < 40 and 0 < tot < 0x100000):
        return None
    o, blocks = base + 16, {}
    for _ in range(nh):
        name, o = pstr(o)
        if not name.isalnum():
            return None
        blocks[name] = u32(o)
        o += 4
    return blocks


def dvfs(b):
    pv, nd, o = i32(b), i32(b + 8), b + 12
    doms = []
    for _ in range(nd):
        name, o = pstr(o)
        doms.append((name, u32(o)))
        o += 4
    for name, off in doms:
        a = b + off
        mx, mn = u32(a), u32(a + 4)
        a += 16 if pv >= 2 else 8
        nc, nl = i32(a), i32(a + 4)
        a += 8
        clks = []
        for _ in range(nc):
            c, a = pstr(a)
            clks.append(c)
        lv = [(u32(a + 8 * i), i32(a + 8 * i + 4)) for i in range(nl)]
        a += 8 * nl
        print('DVFS %s max=%d min=%d clocks=%s' % (name, mx, mn, clks))
        if 'cpu' in name.lower():
            for i, (f, en) in enumerate(lv):
                vals = [u32(a + 4 * (i * nc + k)) for k in range(nc)]
                print('  L%-2d %7d en=%d %s' % (i, f, en, vals))


def pll(b):
    n, o = u32(b + 8), b + 12
    plls = []
    for _ in range(n):
        name, o = pstr(o)
        plls.append((name, u32(o)))
        o += 4
    for name, off in plls:
        a = b + off
        typ, nf = u32(a), u32(a + 4)
        print('PLL %s type %d, %d rates' % (name, typ, nf))
        if 'CPU' in name:
            for i in range(nf):
                f, p, m, s, k = struct.unpack_from('<5I', d, a + 8 + 20 * i)
                print('  %10d p=%d m=%d s=%d k=%d' % (f, p, m, s, k))


pos = 0
while (pos := d.find(b'PARA', pos)) >= 0:
    blocks = headers(pos)
    if blocks and 'DVFS' in blocks:
        print('ECT at %#x, version %r, blocks %s' % (pos, d[pos + 4:pos + 8], blocks))
        dvfs(pos + blocks['DVFS'])
        if 'PLL' in blocks:
            pll(pos + blocks['PLL'])
        break
    pos += 4
else:
    sys.exit('no ECT found')
