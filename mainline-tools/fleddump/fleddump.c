// SPDX-License-Identifier: GPL-2.0
/* read-only dump of an S2MPU06 SPEEDY block (default FLED, blk 6) */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>

struct regmap *devm_exynos_speedy_regmap(struct device *dev, unsigned int blkid);

static uint blk = 6;
module_param(blk, uint, 0444);
static uint last = 0x0f;
module_param(last, uint, 0444);

static int __init fleddump_init(void)
{
	struct device_node *np;
	struct platform_device *speedy, *pdev;
	struct regmap *map;
	unsigned int r, v;

	np = of_find_compatible_node(NULL, NULL, "samsung,s2mpu06-pmic");
	if (!np)
		return -ENODEV;
	speedy = of_find_device_by_node(np->parent);
	of_node_put(np);
	if (!speedy)
		return -ENODEV;

	pdev = platform_device_register_data(&speedy->dev, "fleddump", -1, NULL, 0);
	if (IS_ERR(pdev)) {
		put_device(&speedy->dev);
		return PTR_ERR(pdev);
	}
	map = devm_exynos_speedy_regmap(&pdev->dev, blk);
	if (IS_ERR(map)) {
		pr_err("fleddump: regmap %ld\n", PTR_ERR(map));
	} else {
		for (r = 0; r <= last; r++) {
			int ret = regmap_read(map, r, &v);
			pr_info("fleddump: blk%u 0x%02x = %s0x%02x\n", blk, r,
				ret ? "ERR " : "", ret ? 0 : v);
		}
	}
	platform_device_unregister(pdev);
	put_device(&speedy->dev);
	return -EAGAIN; /* never stay loaded */
}
module_init(fleddump_init);
MODULE_LICENSE("GPL");
