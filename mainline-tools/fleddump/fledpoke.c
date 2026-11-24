// SPDX-License-Identifier: GPL-2.0
/* S2MPU06 FLED torch test: torch at iset (20 mA * (iset+1)) for ms, then restore */
#include <linux/delay.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>

struct regmap *devm_exynos_speedy_regmap(struct device *dev, unsigned int blkid);

static uint iset;
module_param(iset, uint, 0444);
static uint ms = 5000;
module_param(ms, uint, 0444);
static uint ctrl0_set = 0x04;	/* CHGVIN_EN (cable present) */
module_param(ctrl0_set, uint, 0444);
static uint ctrl4_set = 0x8f;	/* TORCH_TMR_MODE | TIMEOUT max, as downstream init */
module_param(ctrl4_set, uint, 0444);

static void dump(struct regmap *m, const char *tag)
{
	unsigned int v[5];
	int i;

	for (i = 0; i < 5; i++)
		regmap_read(m, 3 + i, &v[i]);
	pr_info("fledpoke %s: CTRL0..4 %02x %02x %02x %02x %02x\n", tag,
		v[0], v[1], v[2], v[3], v[4]);
}

static int __init fledpoke_init(void)
{
	struct device_node *np;
	struct platform_device *speedy, *pdev;
	struct regmap *m;
	unsigned int c0, c1, c4;

	np = of_find_compatible_node(NULL, NULL, "samsung,s2mpu06-pmic");
	if (!np)
		return -ENODEV;
	speedy = of_find_device_by_node(np->parent);
	of_node_put(np);
	if (!speedy)
		return -ENODEV;
	pdev = platform_device_register_data(&speedy->dev, "fledpoke", -1, NULL, 0);
	if (IS_ERR(pdev))
		goto out;
	m = devm_exynos_speedy_regmap(&pdev->dev, 6);
	if (IS_ERR(m))
		goto unreg;

	dump(m, "before");
	regmap_read(m, 3, &c0);
	regmap_read(m, 4, &c1);
	regmap_read(m, 7, &c4);
	regmap_update_bits(m, 7, 0x8f, ctrl4_set & 0x8f);
	regmap_update_bits(m, 3, 0x06, ctrl0_set & 0x06);
	regmap_update_bits(m, 4, 0x0f, iset & 0x0f);
	regmap_update_bits(m, 3, 0x20, 0x20);
	dump(m, "on");
	msleep(ms);
	regmap_update_bits(m, 3, 0x20, 0x00);
	regmap_write(m, 4, c1);
	regmap_write(m, 3, c0);
	regmap_write(m, 7, c4);
	dump(m, "after");
unreg:
	platform_device_unregister(pdev);
out:
	put_device(&speedy->dev);
	return -EAGAIN;
}
module_init(fledpoke_init);
MODULE_LICENSE("GPL");
