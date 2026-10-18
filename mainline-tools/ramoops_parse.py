#!/usr/bin/env python3
"""Decode a raw ramoops window (as dumped by ramretain mode=dump).

Follows fs/pstore/ram_core.c: each zone is a 12-byte header (sig 'DBGC',
start, size), the data, then - with ecc-size set - one RS parity block per
128 data bytes plus one for the header (GF(2^8), poly 0x11d, first root 0,
primitive element 1). Errors are corrected with reedsolo when the zone has ECC.

usage: ramoops_parse.py dump.bin [--record 0x20000] [--console 0x100000]
                        [--pmsg 0x20000] [--ecc 16] [--zone console|dmesgN|pmsg]
Prints the zone text on stdout and a summary on stderr.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pylib'))
try:
    import reedsolo
except ImportError:
    reedsolo = None

ap = argparse.ArgumentParser()
ap.add_argument('dump')
ap.add_argument('--record', type=lambda x: int(x, 0), default=0x20000)
ap.add_argument('--console', type=lambda x: int(x, 0), default=0x100000)
ap.add_argument('--pmsg', type=lambda x: int(x, 0), default=0x20000)
ap.add_argument('--ecc', type=int, default=16)
ap.add_argument('--zone', default='console')
args = ap.parse_args()

d = open(args.dump, 'rb').read()
BLOCK = 128


def zones():
    """(name, offset, size) in ramoops order: dmesg records, console, pmsg."""
    total = len(d)
    cnt = (total - args.console - args.pmsg) // args.record
    off = 0
    for i in range(cnt):
        yield 'dmesg%d' % i, off, args.record
        off += args.record
    yield 'console', off, args.console
    off += args.console
    yield 'pmsg', off, args.pmsg


def correct(rs, data, par):
    """Return (corrected data, symbols corrected, bad)."""
    try:
        res = rs.decode(bytearray(data) + bytearray(par))
        return bytes(res[0]), len(res[2]), False
    except reedsolo.ReedSolomonError:
        return bytes(data), 0, True


def read_zone(name, off, size):
    hdr = d[off:off + 12]
    sig = hdr[:4]
    buffer_size = size - 12
    ecc = args.ecc
    fixed = bad = 0
    if ecc:
        blocks = -(-(buffer_size - ecc) // (BLOCK + ecc))
        data_size = buffer_size - (blocks + 1) * ecc
        par = off + 12 + data_size
        par_hdr = par + blocks * ecc
        if reedsolo:
            rs = reedsolo.RSCodec(ecc, nsize=255, fcr=0, prim=0x11d, generator=2, c_exp=8)
            hdr, n, b = correct(rs, hdr, d[par_hdr:par_hdr + ecc])
            fixed += n
            bad += b
    else:
        data_size = buffer_size
    sig = hdr[:4]
    start, sz = struct.unpack_from('<II', hdr, 4)
    if sig != b'DBGC':
        return name, None, 'no DBGC signature (%r)' % sig, 0, 0
    raw = d[off + 12:off + 12 + data_size]
    if ecc and reedsolo:
        # only blocks holding log data have valid parity; the unused tail of the
        # zone is stale memory and would show up as "bad" blocks
        used = blocks if sz >= data_size else -(-sz // BLOCK)
        out = bytearray()
        for i in range(blocks):
            blk = raw[i * BLOCK:(i + 1) * BLOCK]
            if not blk:
                break
            if i >= used:
                out += blk
                continue
            p = d[par + i * ecc:par + (i + 1) * ecc]
            c, n, b = correct(rs, blk, p)
            fixed += n
            bad += b
            out += c
        raw = bytes(out)
        info_extra = ' (%d data blocks checked)' % used
    else:
        info_extra = ''
    if sz > data_size or start > data_size:
        return name, None, 'implausible header start=%d size=%d (data %d)' % (start, sz, data_size), fixed, bad
    text = raw[start:sz] + raw[:start] if sz >= data_size else raw[:sz]
    if sz >= data_size:
        text = raw[start:] + raw[:start]
    return name, text, 'start=%d size=%d data=%d%s' % (start, sz, data_size, info_extra), fixed, bad


want = args.zone
found = False
for name, off, size in zones():
    n, text, info, fixed, bad = read_zone(name, off, size)
    sys.stderr.write('%-8s @0x%06x size 0x%x: %s%s\n' % (
        n, off, size, info,
        '' if not args.ecc else ' [ecc: %d symbols corrected, %d bad blocks%s]' % (
            fixed, bad, '' if reedsolo else ', NO RS LIB')))
    if n == want:
        found = True
        if text is not None:
            sys.stdout.buffer.write(text)
            if not text.endswith(b'\n'):
                sys.stdout.buffer.write(b'\n')
if not found:
    sys.exit('zone %r not found' % want)
