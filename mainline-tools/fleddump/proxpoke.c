// SPDX-License-Identifier: GPL-2.0
/* GP2AP070S test: downstream J4 init, sample D0 every 500 ms, shut down again */
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/module.h>

static int bus = 3;
module_param(bus, int, 0444);
static int samples = 24;
module_param(samples, int, 0444);

static const u8 init[][2] = {
	{ 0x80, 0x00 },	/* COM1 shutdown */
	{ 0x81, 0x00 },	/* COM2 clear all int */
	{ 0x82, 0x02 },	/* COM3 pulse */
	{ 0x83, 0x03 },	/* COM4 intval 33 (J4 DT reg_intval) */
	{ 0x85, 0x20 },	/* PS1 (reg_res_p) */
	{ 0x86, 0x24 },	/* PS2 (reg_ledctrl) */
	{ 0x87, 0x38 },	/* PS3 (reg_prst) */
	{ 0x88, 60 }, { 0x89, 0 },	/* low threshold */
	{ 0x8a, 110 }, { 0x8b, 0 },	/* high threshold */
	{ 0x8c, 65 }, { 0x8d, 0 },	/* offset */
};

static int __init proxpoke_init(void)
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
	for (i = 0; i < ARRAY_SIZE(init); i++)
		i2c_smbus_write_byte_data(c, init[i][0], init[i][1]);
	i2c_smbus_write_byte_data(c, 0x80, 0xa0);	/* wakeup | PS */
	for (i = 0; i < samples; i++) {
		msleep(500);
		pr_info("proxpoke: t=%d.%d D0=%d COM2=0x%02x\n", (i + 1) / 2, (i + 1) % 2 * 5,
			i2c_smbus_read_word_data(c, 0x90),
			i2c_smbus_read_byte_data(c, 0x81));
	}
	i2c_smbus_write_byte_data(c, 0x80, 0x00);	/* shutdown */
	i2c_unregister_device(c);
	i2c_put_adapter(ad);
	return -EAGAIN;
}
module_init(proxpoke_init);
MODULE_LICENSE("GPL");
