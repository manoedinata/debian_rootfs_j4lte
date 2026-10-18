// SPDX-License-Identifier: GPL-2.0
/*
 * ramretain: check whether a physical RAM window survives a reset.
 *
 *   insmod ramretain.ko addr=0x7e100000 size=0x100000 mode=write seed=1
 *   (reset: panic / watchdog / reboot)
 *   insmod ramretain.ko addr=0x7e100000 size=0x100000 mode=check seed=1
 *
 * mode=dump copies the window and stays loaded, exposing it as
 * /sys/kernel/debug/ramretain (for reading a ramoops buffer after a crash;
 * rmmod ramretain to drop it).
 *
 * The window must be memory the kernel does not use (reserved-memory). It is mapped write-combine so no dirty cache lines are lost
 * across a warm reset, mirroring how pstore/ram maps its region.
 */
#include <linux/module.h>
#include <linux/io.h>
#include <linux/vmalloc.h>
#include <linux/mm.h>
#include <linux/slab.h>
#include <linux/debugfs.h>
#include <linux/string.h>

static unsigned long addr;
static unsigned long size = 0x100000;
static char *mode = "check";
static unsigned long seed = 1;
module_param(addr, ulong, 0);
module_param(size, ulong, 0);
module_param(mode, charp, 0);
module_param(seed, ulong, 0);

static struct debugfs_blob_wrapper blob;
static struct dentry *blob_dentry;

static u64 pat(unsigned long i)
{
	u64 x = (i + seed) * 0x9E3779B97F4A7C15ULL;

	return x ^ (x >> 29);
}

static int __init ramretain_init(void)
{
	void *p;
	struct page **pages;
	unsigned long npages;
	unsigned long i, n = size / sizeof(u64);
	unsigned long match = 0, zero = 0, ones = 0, other = 0, first_bad = ~0UL;
	u64 v;

	if (!addr)
		return -EINVAL;

	/* RAM stays pfn_valid, so ioremap refuses it: vmap the pages WC */
	npages = size >> PAGE_SHIFT;
	pages = kcalloc(npages, sizeof(*pages), GFP_KERNEL);
	if (!pages)
		return -ENOMEM;
	for (i = 0; i < npages; i++)
		pages[i] = pfn_to_page((addr >> PAGE_SHIFT) + i);
	p = vmap(pages, npages, VM_MAP, pgprot_writecombine(PAGE_KERNEL));
	kfree(pages);
	if (!p)
		return -ENOMEM;

	if (!strcmp(mode, "dump")) {
		blob.data = vmalloc(size);
		if (!blob.data) {
			vunmap(p);
			return -ENOMEM;
		}
		memcpy(blob.data, p, size);
		blob.size = size;
		blob_dentry = debugfs_create_blob("ramretain", 0400, NULL, &blob);
		pr_info("ramretain: dumped 0x%lx bytes from 0x%lx\n", size, addr);
		vunmap(p);
		return 0;
	}

	if (!strcmp(mode, "write")) {
		for (i = 0; i < n; i++)
			((u64 *)p)[i] = pat(i);
		wmb();
		pr_info("ramretain: wrote %lu words at 0x%lx seed=%lu\n", n, addr, seed);
	} else {
		for (i = 0; i < n; i++) {
			v = ((u64 *)p)[i];
			if (v == pat(i)) {
				match++;
			} else {
				if (first_bad == ~0UL)
					first_bad = i;
				if (!v)
					zero++;
				else if (v == ~0ULL)
					ones++;
				else
					other++;
			}
		}
		pr_info("ramretain: 0x%lx: %lu/%lu match, %lu zero, %lu ones, %lu other (first bad word %ld)\n",
			addr, match, n, zero, ones, other, (long)first_bad);
		if (first_bad != ~0UL)
			pr_info("ramretain: word[%lu]=0x%016llx want 0x%016llx\n", first_bad,
				(unsigned long long)((u64 *)p)[first_bad],
				(unsigned long long)pat(first_bad));
	}
	vunmap(p);
	return -EAGAIN;	/* don't stay loaded; result is in dmesg */
}
static void __exit ramretain_exit(void)
{
	debugfs_remove(blob_dentry);
	vfree(blob.data);
}
module_init(ramretain_init);
module_exit(ramretain_exit);
MODULE_LICENSE("GPL");
