// SPDX-License-Identifier: GPL-2.0
/*
 * cpboot: does the EL3 monitor verify a CP (Shannon modem) image under
 * mainline? Replays what libsamsung-ipc's herolte boot path makes the
 * downstream modem_v1 driver do, up to the signature check, and stops there:
 *
 *   1. SSS clock on, SMC 0x82000700 mode 2 (CP_BOOT_RE_INIT, 0, 0), SSS off
 *   2. BOOT, MAIN (from the RADIO partition, placed by its TOC) and NV
 *      (/efs/nv_data.bin) copied into the boot region of the modem carveout,
 *      at loadaddr - BOOT's loadaddr, like IOCTL_DPRAM_SEND_BOOT
 *   3. SSS clock on, SMC 0x82000700 mode 0 (CP_BOOT_MODE_NORMAL, BOOT size,
 *      MAIN size), SSS off; downstream returns 0 here
 *   4. CP_CTRL_S / CP_CTRL_NS read through EL3 (0xb until an image verified)
 *
 * With start=1 it goes on like ss310ap_on(): the CP mailbox shared registers
 * are cleared and set up as downstream logs them on this phone (sys_rev 2,
 * ds_det 0, cp_cpu_freq_asv 1, pda_active, CP voltages 750000/818750 uV),
 * CP_START is set in CP_CTRL_S and the CP's status field in ISSR3 is polled
 * for 2 s; downstream reads cp_status 1 there once the CP's boot loader runs.
 * The CP is left running (it waits for the AP's boot handshake); a reboot
 * resets it.
 *
 *   insmod cpboot.ko [radio=/dev/mmcblk0p12] [nv=/efs/nv_data.bin] [start=1]
 */
#include <linux/arm-smccc.h>
#include <linux/bitfield.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/string.h>

#define CP_SMC_ID		0x82000700
#define CP_BOOT_MODE_NORMAL	0x0
#define CP_BOOT_RE_INIT		0x2
#define CP_READ_CTRL		0x3
#define CP_WRITE_CTRL		0x4
#define CP_CTRL_S		0
#define CP_CTRL_NS		1
#define CP_PWRON		BIT(1)
#define CP_START		BIT(3)
#define SSS_SMC_ID_CLK		0x82001011

/* exynos7570-rmem.dtsi modem_if, modem-ss305ap-pdata.dtsi shmem,ipc_offset */
#define CP_CARVEOUT_BASE	0x73400000
#define CP_BOOT_REGION_SIZE	0x5800000

#define CHUNK			SZ_64K

/* CMU_MIF CLK_ENABLE_CLK_MIF_APB, bit 22 = MAILBOX_CEL (pwrcal S5E7570-cmu.c) */
#define CMU_MIF_APB_ENABLE	0x10460814
#define MAILBOX_CEL_GATE	BIT(22)

/* mailbox_cp, regs-mcu_ipc.h; shared registers ISSR0..63 */
#define MBOX_CP_BASE		0x10500000
#define MBOX_SIZE		0x180
#define MBOX_INTSR0		0x14
#define MBOX_INTSR1		0x28
#define MBOX_ISSR(n)		(0x80 + 4 * (n))
#define MBOX_NUM		64

/* modem-ss305ap-pdata.dtsi */
#define MBX_AP2CP_STATUS	2
#define MBX_CP2AP_STATUS	3
#define MBX_CP_VOLT_700		5
#define MBX_CP_VOLT_830		7
#define SBI_PDA_ACTIVE		BIT(5)
#define SBI_SYS_REV_POS		6
#define SBI_DS_DET_POS		14
#define SBI_CP_ASV_POS		19
#define SBI_CP_STATUS		GENMASK(4, 1)

/* this phone's values, from the downstream log */
#define J4_SYS_REV		2
#define J4_DS_DET		0
#define J4_CP_ASV		1
#define J4_CP_VOLT_700		750000
#define J4_CP_VOLT_830		818750

static char *radio = "/dev/mmcblk0p12";
module_param(radio, charp, 0);
static char *nv = "/efs/nv_data.bin";
module_param(nv, charp, 0);
static int start;
module_param(start, int, 0);

struct toc_entry {
	char name[12];
	__le32 offset;		/* in the partition */
	__le32 loadaddr;	/* in the CP's view */
	__le32 size;
	__le32 crc;
	__le32 entryid;
} __packed;

#define N_TOC (512 / sizeof(struct toc_entry))

static const struct toc_entry *find_toc(const struct toc_entry *toc, const char *name)
{
	int i;

	for (i = 0; i < N_TOC; i++)
		if (!strncmp(toc[i].name, name, sizeof(toc[i].name)))
			return &toc[i];
	return NULL;
}

static unsigned long cp_smc(unsigned long a1, unsigned long a2, unsigned long a3)
{
	struct arm_smccc_res res;

	arm_smccc_smc(SSS_SMC_ID_CLK, 0, 0, 0, 0, 0, 0, 0, &res);
	pr_info("cpboot: SSS clk on -> 0x%lx\n", res.a0);
	arm_smccc_smc(CP_SMC_ID, a1, a2, a3, 0, 0, 0, 0, &res);
	pr_info("cpboot: SMC mode %lu (%#lx, %#lx) -> 0x%lx\n", a1, a2, a3, res.a0);
	a1 = res.a0;
	arm_smccc_smc(SSS_SMC_ID_CLK, 1, 0, 0, 0, 0, 0, 0, &res);
	pr_info("cpboot: SSS clk off -> 0x%lx\n", res.a0);

	return a1;
}

/* copies len bytes at pos of path to dst, through a bounce buffer */
static int load(void __iomem *dst, const char *path, loff_t pos, size_t len, void *buf)
{
	struct file *f;
	size_t done = 0;
	ssize_t n;
	int ret = 0;

	f = filp_open(path, O_RDONLY, 0);
	if (IS_ERR(f)) {
		pr_err("cpboot: cannot open %s: %ld\n", path, PTR_ERR(f));
		return PTR_ERR(f);
	}

	while (done < len) {
		n = kernel_read(f, buf, min_t(size_t, CHUNK, len - done), &pos);
		if (n <= 0) {
			pr_err("cpboot: %s: read at %zu of %zu failed: %zd\n", path, done, len, n);
			ret = n ? n : -EIO;
			break;
		}
		memcpy_toio(dst + done, buf, n);
		done += n;
	}

	filp_close(f, NULL);
	return ret;
}

static int read_toc(void *toc)
{
	loff_t pos = 0;
	struct file *f;
	ssize_t n;

	f = filp_open(radio, O_RDONLY, 0);
	if (IS_ERR(f)) {
		pr_err("cpboot: cannot open %s: %ld\n", radio, PTR_ERR(f));
		return PTR_ERR(f);
	}
	n = kernel_read(f, toc, 512, &pos);
	filp_close(f, NULL);

	return n == 512 ? 0 : -EIO;
}

static void read_ctrl(void)
{
	static const char * const names[] = { "CP_CTRL_S", "CP_CTRL_NS" };
	struct arm_smccc_res res;
	unsigned int reg, half;

	for (reg = 0; reg < 2; reg++)
		for (half = 0; half < 2; half++) {
			arm_smccc_smc(CP_SMC_ID, CP_READ_CTRL, half, reg, 0, 0, 0, 0, &res);
			pr_info("cpboot: %s half %u -> x0=0x%lx\n", names[reg], half, res.a0);
		}
}

/* pmu-cp.c exynos_smc_read(): two halves, 0 in bits 15:0 on success */
static int ctrl_read(unsigned int reg, u32 *val)
{
	struct arm_smccc_res lo, hi;

	arm_smccc_smc(CP_SMC_ID, CP_READ_CTRL, 0, reg, 0, 0, 0, 0, &lo);
	arm_smccc_smc(CP_SMC_ID, CP_READ_CTRL, 1, reg, 0, 0, 0, 0, &hi);
	if ((lo.a0 & 0xffff) || (hi.a0 & 0xffff))
		return -EIO;

	*val = ((u32)hi.a0 >> 16) << 16 | (u32)lo.a0 >> 16;
	return 0;
}

static int ctrl_write(unsigned int reg, u32 val)
{
	struct arm_smccc_res res;

	arm_smccc_smc(CP_SMC_ID, CP_WRITE_CTRL, val, reg, 0, 0, 0, 0, &res);
	return (int)res.a0 > 0 ? -EIO : 0;
}

static void mbox_dump(void __iomem *mbox, const char *when)
{
	int i;

	pr_info("cpboot: mailbox %s: INTSR0 %#x INTSR1 %#x\n", when,
		readl(mbox + MBOX_INTSR0), readl(mbox + MBOX_INTSR1));
	for (i = 0; i < 8; i++)
		pr_info("cpboot:   ISSR%d = %#x\n", i, readl(mbox + MBOX_ISSR(i)));
}

/* ss310ap_on(): init_mailbox_regs(), pda_active, then CP_START */
static int cp_start(void)
{
	void __iomem *gate, *mbox;
	u32 ns, s, st = 0;
	int i, ret;

	gate = ioremap(CMU_MIF_APB_ENABLE, 4);
	if (!gate)
		return -ENOMEM;
	i = readl(gate);
	iounmap(gate);
	pr_info("cpboot: CMU_MIF APB gates %#x\n", i);
	if (!(i & MAILBOX_CEL_GATE)) {
		pr_err("cpboot: the CP mailbox clock is gated, not touching it\n");
		return -EIO;
	}

	mbox = ioremap(MBOX_CP_BASE, MBOX_SIZE);
	if (!mbox)
		return -ENOMEM;
	mbox_dump(mbox, "before");

	for (i = 0; i < MBOX_NUM; i++)
		writel(0, mbox + MBOX_ISSR(i));
	writel(J4_SYS_REV << SBI_SYS_REV_POS | J4_DS_DET << SBI_DS_DET_POS |
	       J4_CP_ASV << SBI_CP_ASV_POS | SBI_PDA_ACTIVE, mbox + MBOX_ISSR(MBX_AP2CP_STATUS));
	writel(J4_CP_VOLT_700, mbox + MBOX_ISSR(MBX_CP_VOLT_700));
	writel(J4_CP_VOLT_830, mbox + MBOX_ISSR(MBX_CP_VOLT_830));

	ret = ctrl_read(CP_CTRL_NS, &ns);
	if (!ret)
		ret = ctrl_read(CP_CTRL_S, &s);
	if (ret) {
		pr_err("cpboot: CP_CTRL unreadable\n");
		goto out;
	}
	pr_info("cpboot: CP_CTRL_NS %#x CP_CTRL_S %#x\n", ns, s);

	/* exynos_set_cp_power_onoff(CP_POWER_ON) / exynos_cp_release() */
	if (!(ns & CP_PWRON)) {
		ret = ctrl_write(CP_CTRL_NS, ns | CP_PWRON);
		pr_info("cpboot: CP power on -> %d\n", ret);
		if (ret)
			goto out;
	}
	ret = ctrl_write(CP_CTRL_S, s | CP_START);
	ctrl_read(CP_CTRL_S, &s);
	pr_info("cpboot: CP start -> %d, CP_CTRL_S now %#x\n", ret, s);
	if (ret)
		goto out;

	for (i = 0; i < 40; i++) {
		msleep(50);
		st = FIELD_GET(SBI_CP_STATUS, readl(mbox + MBOX_ISSR(MBX_CP2AP_STATUS)));
		if (st)
			break;
	}
	pr_info("cpboot: cp_status %u after %d ms\n", st, (i + 1) * 50);
	mbox_dump(mbox, "after");
	ret = st ? 0 : -ETIMEDOUT;
out:
	iounmap(mbox);
	return ret;
}

static int place(void __iomem *base, const struct toc_entry *boot,
		 const struct toc_entry *e, const char *path, loff_t pos, void *buf)
{
	u32 off = le32_to_cpu(e->loadaddr) - le32_to_cpu(boot->loadaddr);
	u32 size = le32_to_cpu(e->size);

	if (off > CP_BOOT_REGION_SIZE || size > CP_BOOT_REGION_SIZE - off) {
		pr_err("cpboot: %.12s at %#x size %#x does not fit\n", e->name, off, size);
		return -EINVAL;
	}
	pr_info("cpboot: %.12s: %s+%#llx -> carveout+%#x, %#x bytes\n",
		e->name, path, pos, off, size);

	return load(base + off, path, pos, size, buf);
}

static int __init cpboot_init(void)
{
	const struct toc_entry *boot, *main, *nvent;
	struct toc_entry *toc;
	void __iomem *base;
	void *buf;
	int ret;

	buf = kmalloc(CHUNK, GFP_KERNEL);
	if (!buf)
		return -ENOMEM;
	toc = buf;

	ret = read_toc(toc);
	if (ret)
		goto out_free;

	boot = find_toc(toc, "BOOT");
	main = find_toc(toc, "MAIN");
	nvent = find_toc(toc, "NV");
	if (!boot || !main || !nvent) {
		pr_err("cpboot: TOC lacks BOOT/MAIN/NV\n");
		ret = -EINVAL;
		goto out_free;
	}
	/* keep the entries, buf is reused as the bounce buffer */
	toc = kmemdup(toc, 512, GFP_KERNEL);
	if (!toc) {
		ret = -ENOMEM;
		goto out_free;
	}
	boot = find_toc(toc, "BOOT");
	main = find_toc(toc, "MAIN");
	nvent = find_toc(toc, "NV");

	pr_info("cpboot: before anything:\n");
	read_ctrl();

	cp_smc(CP_BOOT_RE_INIT, 0, 0);

	base = ioremap_wc(CP_CARVEOUT_BASE, CP_BOOT_REGION_SIZE);
	if (!base) {
		ret = -ENOMEM;
		goto out_toc;
	}
	ret = place(base, boot, boot, radio, le32_to_cpu(boot->offset), buf);
	if (!ret)
		ret = place(base, boot, main, radio, le32_to_cpu(main->offset), buf);
	if (!ret)
		ret = place(base, boot, nvent, nv, 0, buf);
	wmb();
	iounmap(base);
	if (ret)
		goto out_toc;

	ret = cp_smc(CP_BOOT_MODE_NORMAL, le32_to_cpu(boot->size), le32_to_cpu(main->size));
	pr_info("cpboot: signature check %s\n", ret ? "FAILED" : "passed");

	pr_info("cpboot: after mode 0:\n");
	read_ctrl();

	if (start && !ret)
		pr_info("cpboot: CP start %s\n", cp_start() ? "FAILED" : "ok");
	ret = -EAGAIN;

out_toc:
	kfree(toc);
out_free:
	kfree(buf);
	return ret;
}
module_init(cpboot_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Exynos7570 CP image verification test");
