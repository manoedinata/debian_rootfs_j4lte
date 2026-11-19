// SPDX-License-Identifier: GPL-2.0
/*
 * ocvolt: hold a minimum voltage on the CPU supply (BUCK1 on the J4) for
 * overclock tests. The regulator core applies the highest of the consumers'
 * minimums, so this can only raise what cpufreq asks for, never lower it.
 *
 *   insmod ocvolt.ko uv=1100000
 *   echo 1050000 > /sys/module/ocvolt/parameters/uv     (0 drops the request)
 *   rmmod ocvolt
 */
#include <linux/cpu.h>
#include <linux/module.h>
#include <linux/regulator/consumer.h>

#define OCVOLT_MAX	1100000

static struct regulator *reg;
static int uv;

static int ocvolt_apply(int val)
{
	if (!reg)
		return 0;
	if (val <= 0)
		return regulator_set_voltage(reg, 0, OCVOLT_MAX);
	return regulator_set_voltage(reg, val, OCVOLT_MAX);
}

static int uv_set(const char *val, const struct kernel_param *kp)
{
	int v, ret;

	ret = kstrtoint(val, 0, &v);
	if (ret)
		return ret;
	if (v > OCVOLT_MAX)
		return -EINVAL;
	ret = ocvolt_apply(v);
	if (ret)
		return ret;
	uv = v;
	pr_info("ocvolt: minimum %d uV, supply now %d uV\n", v,
		reg ? regulator_get_voltage(reg) : -1);
	return 0;
}

static const struct kernel_param_ops uv_ops = {
	.set = uv_set,
	.get = param_get_int,
};
module_param_cb(uv, &uv_ops, &uv, 0644);

static int __init ocvolt_init(void)
{
	struct device *cpu = get_cpu_device(0);
	int ret;

	if (!cpu)
		return -ENODEV;
	reg = regulator_get(cpu, "cpu");
	if (IS_ERR(reg)) {
		ret = PTR_ERR(reg);
		reg = NULL;
		return ret;
	}
	ret = ocvolt_apply(uv);
	if (ret) {
		regulator_put(reg);
		reg = NULL;
		return ret;
	}
	pr_info("ocvolt: minimum %d uV, supply now %d uV\n", uv,
		regulator_get_voltage(reg));
	return 0;
}

static void __exit ocvolt_exit(void)
{
	regulator_set_voltage(reg, 0, OCVOLT_MAX);
	regulator_put(reg);
}

module_init(ocvolt_init);
module_exit(ocvolt_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Minimum CPU supply voltage for overclock tests");
