// SPDX-License-Identifier: GPL-2.0
/*
 * cpprobe for the downstream 3.18 kernel: the same EL3 CP control reads as
 * mainline-tools/cpprobe, to tell whether the 0xb answers on mainline are the
 * normal state of a CP that has not been booted.
 *
 * SMC 0x82000700, READ_CTRL (3), arg2 = half (0 = low 16 bits, 1 = high),
 * arg3 = CP_CTRL_S (0) / CP_CTRL_NS (1). A good reply has 0 in bits 15:0 and
 * the register half in bits 31:16. exynos_smc() is not exported here, so the
 * smc is issued inline. Read-only; init returns -EAGAIN, nothing stays loaded.
 */
#include <linux/module.h>
#include <linux/kernel.h>

#define CP_SMC_ID	0x82000700
#define CP_READ_CTRL	0x3

static noinline u64 cpprobe_smc(u64 a0, u64 a1, u64 a2, u64 a3, u64 *r1)
{
	register u64 x0 asm("x0") = a0;
	register u64 x1 asm("x1") = a1;
	register u64 x2 asm("x2") = a2;
	register u64 x3 asm("x3") = a3;

	asm volatile("smc #0"
		     : "+r" (x0), "+r" (x1), "+r" (x2), "+r" (x3)
		     :
		     : "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12",
		       "x13", "x14", "x15", "x16", "x17", "memory");
	*r1 = x1;
	return x0;
}

static const char * const names[] = { "CP_CTRL_S", "CP_CTRL_NS" };

static int __init cpprobe_init(void)
{
	unsigned int reg, half;
	u64 a0, a1;
	u32 r[2];

	for (reg = 0; reg < 2; reg++) {
		for (half = 0; half < 2; half++) {
			a0 = cpprobe_smc(CP_SMC_ID, CP_READ_CTRL, half, reg, &a1);
			r[half] = (u32)a0;
			pr_info("cpprobe: %s half %u -> x0=0x%016llx x1=0x%llx\n",
				names[reg], half, a0, a1);
		}
		if (!(r[0] & 0xffff) && !(r[1] & 0xffff))
			pr_info("cpprobe: %s = 0x%08x\n", names[reg],
				(r[1] >> 16) << 16 | r[0] >> 16);
		else
			pr_info("cpprobe: %s read failed\n", names[reg]);
	}
	return -EAGAIN;
}
module_init(cpprobe_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Read Exynos7570 CP control registers via EL3 (downstream)");
