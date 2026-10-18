// SPDX-License-Identifier: GPL-2.0
/*
 * regpeek: read (and optionally write) 32-bit device registers from the
 * downstream kernel, for bring-up of the mainline port.
 *
 *   insmod regpeek.ko addr=0x13731000 count=2          (dmesg shows the values)
 *   insmod regpeek.ko addr=0x13731000 count=1 wval=0x5 do_write=1
 *
 * The module never stays loaded (init returns -EAGAIN).
 */
#include <linux/module.h>
#include <linux/io.h>

static unsigned long addr;
static unsigned int count = 1;
static unsigned int wval;
static int do_write;
module_param(addr, ulong, 0);
module_param(count, uint, 0);
module_param(wval, uint, 0);
module_param(do_write, int, 0);

static int __init regpeek_init(void)
{
	void __iomem *p;
	unsigned int i;

	if (!addr || (addr & 3) || !count || count > 256)
		return -EINVAL;
	p = ioremap(addr, count * 4);
	if (!p)
		return -ENOMEM;
	if (do_write) {
		pr_info("regpeek: 0x%08lx <- 0x%08x\n", addr, wval);
		writel(wval, p);
	}
	for (i = 0; i < count; i++)
		pr_info("regpeek: 0x%08lx = 0x%08x\n", addr + i * 4, readl(p + i * 4));
	iounmap(p);
	return -EAGAIN;
}
module_init(regpeek_init);
MODULE_LICENSE("GPL");
