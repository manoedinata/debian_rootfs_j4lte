// SPDX-License-Identifier: GPL-2.0
/* read-only register dump of the GP2AP070S at 0x39 on an i2c bus */
#include <linux/i2c.h>
#include <linux/module.h>

static int bus = 3;
module_param(bus, int, 0444);

static const u8 regs[] = { 0x80, 0x81, 0x82, 0x83, 0x85, 0x86, 0x87, 0x88, 0x89,
			   0x8a, 0x8b, 0x8c, 0x8d, 0x8e, 0x90, 0x91, 0xa0, 0xa1 };

static int __init proxdump_init(void)
{
	struct i2c_adapter *ad = i2c_get_adapter(bus);
	struct i2c_client *c;
	int i;

	if (!ad)
		return -ENODEV;
	c = i2c_new_dummy_device(ad, 0x39);
	if (IS_ERR(c)) {
		i2c_put_adapter(ad);
		return PTR_ERR(c);
	}
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		int v = i2c_smbus_read_byte_data(c, regs[i]);

		pr_info("proxdump: 0x%02x = %d (0x%02x)\n", regs[i], v, v & 0xff);
	}
	i2c_unregister_device(c);
	i2c_put_adapter(ad);
	return -EAGAIN;
}
module_init(proxdump_init);
MODULE_LICENSE("GPL");
