// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (c) 2022, Ivaylo Ivanov <ivo.ivanov.ivanov1@gmail.com>
 * Copyright (c) 2026, Igor Belwon <igor.belwon@mentallysanemainliners.org>
 *
 * J4 bring-up variant: report the CPU state, check the Image magic, and make the
 * copied kernel/ramdisk/dtb visible to the next stage before jumping (the
 * arm64 boot protocol wants them in memory, and instruction fetch must not
 * see stale lines of whatever S-BOOT left at the destination).
 */

#include <main/boot.h>
#include <string.h>
#include <lib/debug.h>

static void sync_range(unsigned long start, unsigned long size)
{
	unsigned long ctr, line, a;

	asm volatile("mrs %0, ctr_el0" : "=r"(ctr));
	line = 4UL << ((ctr >> 16) & 0xf);	/* D-cache line size */

	for (a = start & ~(line - 1); a < start + size; a += line)
		asm volatile("dc civac, %0" :: "r"(a) : "memory");
	asm volatile("dsb sy" ::: "memory");
}

/* arch counter, 26 MHz on this SoC (the kernel dt says S-BOOT does not set CNTFRQ) */
static unsigned long now_ms(void)
{
	unsigned long c;

	asm volatile("isb\n\tmrs %0, cntpct_el0" : "=r"(c));
	return c / 26000;
}

static void sync_code(void)
{
	asm volatile("ic iallu\n\tdsb sy\n\tisb" ::: "memory");
}

void arch_load_kernel(void* kernel, void* dt, void* ramdisk)
{
	unsigned long el, sctlr;
	unsigned long ksize = (unsigned long) &kernel_size;
	unsigned long fdt_size;
	unsigned int magic;
	unsigned long t0, t1, t3;

	asm volatile("mrs %0, CurrentEL" : "=r"(el));
	el >>= 2;
	if (el == 2)
		asm volatile("mrs %0, sctlr_el2" : "=r"(sctlr));
	else
		asm volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
	printk(KERN_INFO, "handoff: EL%u SCTLR=%08x (M=%u C=%u I=%u)\n",
	       (unsigned) el, (unsigned) sctlr, (unsigned) (sctlr & 1),
	       (unsigned) ((sctlr >> 2) & 1), (unsigned) ((sctlr >> 12) & 1));

	t0 = now_ms();
	memcpy((void*)CONFIG_PAYLOAD_ENTRY, kernel, ksize);
#ifndef CONFIG_RAMDISK_NO_COPY
	__optimized_memcpy((void*)CONFIG_RAMDISK_ENTRY, ramdisk, (unsigned long) &ramdisk_size);
#endif

	t1 = now_ms();
	/*
	 * Only the Image magic is checked: a full memcmp runs on uncached memory
	 * (MMU is off) and cost seconds. The copy itself was verified once while
	 * bringing this up.
	 */
	magic = *(volatile unsigned int *)(CONFIG_PAYLOAD_ENTRY + 0x38);
	printk(KERN_INFO, "kernel @%08x size %08x: magic %08x %s\n",
	       (unsigned) CONFIG_PAYLOAD_ENTRY, (unsigned) ksize, magic,
	       magic == 0x644d5241 ? "ok" : "BAD (want 644d5241)");

	/* fdt totalsize is big-endian at +4 */
	fdt_size = __builtin_bswap32(*(volatile unsigned int *)((unsigned long) dt + 4));
	printk(KERN_INFO, "dtb @%08x size %08x, initrd @%08x\n",
	       (unsigned) (unsigned long) dt, (unsigned) fdt_size,
	       (unsigned) CONFIG_RAMDISK_ENTRY);

	sync_range(CONFIG_PAYLOAD_ENTRY, ksize);
#ifndef CONFIG_RAMDISK_NO_COPY
	sync_range(CONFIG_RAMDISK_ENTRY, (unsigned long) &ramdisk_size);
#endif
	sync_range((unsigned long) dt, fdt_size);
	sync_code();
	t3 = now_ms();
	printk(KERN_INFO, "timing: copy %u ms, cache sync %u ms\n",
	       (unsigned) (t1 - t0), (unsigned) (t3 - t1));

	load_kernel_and_jump(dt, 0, 0, 0, (void*)CONFIG_PAYLOAD_ENTRY);
}
