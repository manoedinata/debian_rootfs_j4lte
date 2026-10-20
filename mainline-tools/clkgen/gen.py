#!/usr/bin/env python3
"""Generate mainline clk-exynos7570.c and its dt-bindings header.

Every register offset, bit position, divider width and parent relation is
taken from the downstream Samsung pwrcal sources
(kernel/drivers/soc/samsung/pwrcal/S5E7570); spec.py only selects clocks and
names them. A parent that is not in the spec is an error.

usage: gen.py <repo-root> <linux-src>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec  # noqa: E402

ROOT = sys.argv[1]
LINUX = sys.argv[2]
D = os.path.join(ROOT, 'kernel/drivers/soc/samsung/pwrcal/S5E7570')

# ---------------------------------------------------------------- downstream
regs = {}
for m in re.finditer(r'#define\s+(\w+)\s+\(\(void \*\)\(CMU_(\w+)_BASE \+ (0x[0-9A-Fa-f]+)\)\)',
                     open(os.path.join(D, 'S5E7570-cmusfr.h')).read()):
    regs[m.group(1)] = (m.group(2).lower(), int(m.group(3), 16))

src = re.sub(r'/\*.*?\*/', '', open(os.path.join(D, 'S5E7570-cmu.c')).read(), flags=re.S)

parr = {}
for m in re.finditer(r'static struct pwrcal_clk \*(\w+)\[\]\s*=\s*\{([^}]*)\};', src):
    parr[m.group(1)] = re.findall(r'CLK\((\w+)\)', m.group(2))


def args(s):
    return [a.strip() for a in s.split(',')]


down = {}
for m in re.finditer(r'^(CLK_PLL|FIXEDRATE|FIXEDFACTOR|CLK_MUX|CLK_DIV|CLK_GATE)\(([^;]*?)\);',
                     src, flags=re.M | re.S):
    macro, a = m.group(1), args(m.group(2))
    if macro == 'CLK_PLL':
        down[a[1]] = dict(kind='pll', lock=a[3], con=a[4])
    elif macro == 'FIXEDRATE':
        down[a[0]] = dict(kind='frat', rate=int(eval(a[1], {'MHZ': 1000000, 'KHZ': 1000})))
    elif macro == 'FIXEDFACTOR':
        down[a[0]] = dict(kind='ffac', parent=a[1], ratio=int(a[2]))
    elif macro == 'CLK_MUX':
        down[a[0]] = dict(kind='mux', parents=parr[a[1]], reg=a[2], shift=int(a[3]), width=int(a[4]))
    elif macro == 'CLK_DIV':
        down[a[0]] = dict(kind='div', parent=a[1], reg=a[2], shift=int(a[3]), width=int(a[4]))
    elif macro == 'CLK_GATE':
        down[a[0]] = dict(kind='gate', parent=a[1], reg=a[2], shift=int(a[3]))

# ------------------------------------------------------------------- naming
PFX = {'pll': 'fout', 'mux': 'mout', 'div': 'dout', 'gate': 'gout', 'ffac': 'ffac', 'frat': 'frat'}


def auto_name(kind, ds):
    s = ds.lower().replace('clkcmu', 'cmu')
    if kind == 'pll':
        return 'fout_mif_' + s
    if kind == 'ffac':
        return 'ffac_' + s.replace('_ff_', '_', 1)
    return PFX[kind] + '_' + s.replace('_' + {'mux': 'mux', 'div': 'div', 'gate': 'gate'}[kind] + '_', '_', 1)


names = dict(spec.EXTERNAL)
order = {c: [] for c in spec.SPEC}
for cmu, entries in spec.SPEC.items():
    for kind, ds, name, flags in entries:
        if ds not in down:
            sys.exit('error: %s not found in downstream cmu.c' % ds)
        if down[ds]['kind'] != kind:
            sys.exit('error: %s is %s downstream, spec says %s' % (ds, down[ds]['kind'], kind))
        name = name or auto_name(kind, ds)
        names[ds] = name
        order[cmu].append((kind, ds, name, flags))


for _a, _t in spec.ALIASES.items():
    names[_a] = names[_t]


def pname(ds):
    if ds not in names:
        sys.exit('error: parent %s is not in the spec (needed by a selected clock)' % ds)
    return names[ds]


def clkid(name):
    return 'CLK_' + name.upper()


ids = {}
nr = {}
for cmu, lst in order.items():
    n = 0
    for kind, ds, name, flags in lst:
        if kind in ('pll', 'mux', 'div', 'gate', 'frat'):
            n += 1
            ids[name] = n
    nr[cmu] = n + 1


def rel(regname, cmu):
    c, off = regs[regname]
    if c != cmu:
        sys.exit('error: register %s belongs to CMU_%s, used in CMU_%s' % (regname, c, cmu))
    return off


# ------------------------------------------------------------------- header
hdr = ['/* SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause) */',
       '/*',
       ' * Device Tree binding constants for Exynos7570 clock controller.',
       ' */', '',
       '#ifndef _DT_BINDINGS_CLOCK_EXYNOS7570_H',
       '#define _DT_BINDINGS_CLOCK_EXYNOS7570_H', '']
for cmu, lst in order.items():
    hdr.append('/* CMU_%s */' % cmu.upper())
    for kind, ds, name, flags in sorted((e for e in lst if e[2] in ids), key=lambda e: ids[e[2]]):
        hdr.append('#define %-48s %d' % (clkid(name), ids[name]))
    hdr.append('#define %-48s %d' % ('%s_NR_CLK' % cmu.upper(), nr[cmu]))
    hdr.append('')
hdr.append('#endif /* _DT_BINDINGS_CLOCK_EXYNOS7570_H */')
open(os.path.join(LINUX, 'include/dt-bindings/clock/samsung,exynos7570-cmu.h'), 'w').write('\n'.join(hdr) + '\n')

# ------------------------------------------------------------------- driver
out = ['''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (C) 2016 Samsung Electronics Co., Ltd.
 *
 * Common Clock Framework support for Exynos7570.
 *
 * Register layout, parents and bit positions follow the Samsung downstream
 * "pwrcal" tables for S5E7570. Muxes are modelled by their select field only;
 * the per-mux enable bit (bit 21) is left as the bootloader set it.
 *
 * The USB20 PHY core clock comes from the 20 MHz USB PLL (WPLL), which sits
 * behind the WLBT block. It is registered by hand below and enabled by the AP,
 * the way the downstream kernel does when WLBT firmware is not using it.
 */

#include <linux/clk-provider.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/slab.h>

#include <dt-bindings/clock/samsung,exynos7570-cmu.h>

#include "clk.h"
#include "clk-exynos-arm64.h"
''']


def gate_flags(flags):
    f = []
    if 'crit' in flags:
        f.append('CLK_IS_CRITICAL')
    if 'rate' in flags:
        f.append('CLK_SET_RATE_PARENT')
    return ' | '.join(f) or '0'


for cmu, lst in order.items():
    base = spec.CMUS[cmu]['base']
    used = {}
    for kind, ds, name, flags in lst:
        d = down[ds]
        for key in ('lock', 'con', 'reg'):
            if key in d:
                used[d[key]] = rel(d[key], cmu)
    out.append('/*\n * Register offsets for CMU_%s (0x%08x)\n */' % (cmu.upper(), base))
    for rn, off in sorted(used.items(), key=lambda kv: (kv[1], kv[0])):
        out.append('#define %-48s 0x%04x' % (rn, off))
    out.append('')
    out.append('static const unsigned long %s_clk_regs[] __initconst = {' % cmu)
    for rn, off in sorted(used.items(), key=lambda kv: (kv[1], kv[0])):
        out.append('\t%s,' % rn)
    out.append('};\n')

    kinds = {k: [e for e in lst if e[0] == k] for k in PFX}
    if kinds['frat']:
        out.append('static const struct samsung_fixed_rate_clock %s_fixed_clks[] __initconst = {' % cmu)
        for kind, ds, name, flags in kinds['frat']:
            out.append('\tFRATE(%s, "%s", NULL, 0, %d),' % (clkid(name), name, down[ds]['rate']))
        out.append('};\n')
    if kinds['ffac']:
        out.append('static const struct samsung_fixed_factor_clock %s_fixed_factor_clks[] __initconst = {' % cmu)
        for kind, ds, name, flags in kinds['ffac']:
            d = down[ds]
            out.append('\tFFACTOR(0, "%s", "%s", 1, %d, 0),' % (name, pname(d['parent']), d['ratio']))
        out.append('};\n')
    if kinds['pll']:
        out.append('static const struct samsung_pll_clock %s_pll_clks[] __initconst = {' % cmu)
        for kind, ds, name, flags in kinds['pll']:
            d = down[ds]
            out.append('\tPLL(pll_1417x, %s, "%s", "oscclk", %s, %s, NULL),' % (clkid(name), name, d['lock'], d['con']))
        out.append('};\n')
    if kinds['mux']:
        out.append('/* List of parent clocks for muxes in CMU_%s */' % cmu.upper())
        for kind, ds, name, flags in kinds['mux']:
            ps = ', '.join('"%s"' % pname(p) for p in down[ds]['parents'])
            out.append('PNAME(%s_p) = { %s };' % (name, ps))
        out.append('\nstatic const struct samsung_mux_clock %s_mux_clks[] __initconst = {' % cmu)
        for kind, ds, name, flags in kinds['mux']:
            d = down[ds]
            out.append('\tMUX(%s, "%s", %s_p, %s, %d, %d),' % (clkid(name), name, name, d['reg'], d['shift'], d['width']))
        out.append('};\n')
    if kinds['div']:
        out.append('static const struct samsung_div_clock %s_div_clks[] __initconst = {' % cmu)
        for kind, ds, name, flags in kinds['div']:
            d = down[ds]
            out.append('\tDIV(%s, "%s", "%s", %s, %d, %d),' % (clkid(name), name, pname(d['parent']), d['reg'], d['shift'], d['width']))
        out.append('};\n')
    if kinds['gate']:
        out.append('static const struct samsung_gate_clock %s_gate_clks[] __initconst = {' % cmu)
        for kind, ds, name, flags in kinds['gate']:
            d = down[ds]
            out.append('\tGATE(%s, "%s", "%s", %s, %d, %s, 0),' % (clkid(name), name, pname(d['parent']), d['reg'], d['shift'], gate_flags(flags)))
        out.append('};\n')

    out.append('static const struct samsung_cmu_info %s_cmu_info __initconst = {' % cmu)
    for key, arr in (('fixed_clks', 'fixed'), ('fixed_factor_clks', 'fixed_factor'), ('pll_clks', 'pll'),
                     ('mux_clks', 'mux'), ('div_clks', 'div'), ('gate_clks', 'gate')):
        kk = {'fixed': 'frat', 'fixed_factor': 'ffac', 'pll': 'pll', 'mux': 'mux', 'div': 'div', 'gate': 'gate'}[arr]
        if kinds[kk]:
            out.append('\t.%s\t= %s_%s,' % (key, cmu, key))
            out.append('\t.nr_%s\t= ARRAY_SIZE(%s_%s),' % (key, cmu, key))
    out.append('\t.clk_regs\t\t= %s_clk_regs,' % cmu)
    out.append('\t.nr_clk_regs\t\t= ARRAY_SIZE(%s_clk_regs),' % cmu)
    out.append('\t.nr_clk_ids\t\t= %s_NR_CLK,' % cmu.upper())
    if cmu == 'dispaud':
        out.append('\t.clk_name\t\t= "bus",')   # MIF gate feeding the CMU register bus
    out.append('};\n')

out.append('''/*
 * USB PLL (WPLL), the 20 MHz reference of the USB PHY. The PLL itself is in
 * the WLBT block; USBPLL_CON1 in CMU_FSYS tells who drives it. Without WLBT
 * firmware the AP owns it: select the 26 MHz reference, enable it, hand the
 * ownership to the AP and start the AFC (same steps and 20 us delay as the
 * downstream pwrcal / SCSC code, usbpll,owner = "y", usbpll,udelay = <20>).
 */
#define USBPLL_CON1_OFFSET	0x1004
#define USBPLL_WPLL_SEL		BIT(0)	/* 1: AP owns the PLL, 0: WLBT */
#define USBPLL_WPLL_EN		BIT(1)
#define USBPLL_WPLL_AFC_START	BIT(2)
#define USBPLL_WPLL_FREF_SEL	BIT(3)	/* 1: 52 MHz TCXO, 0: 26 MHz */
#define USBPLL_RATE		20000000

struct exynos7570_wpll {
	struct clk_hw hw;
	void __iomem *con1;
};

#define to_wpll(_hw) container_of(_hw, struct exynos7570_wpll, hw)

static int exynos7570_wpll_prepare(struct clk_hw *hw)
{
	struct exynos7570_wpll *wpll = to_wpll(hw);
	u32 val = readl(wpll->con1);

	if ((val & (USBPLL_WPLL_SEL | USBPLL_WPLL_EN)) ==
	    (USBPLL_WPLL_SEL | USBPLL_WPLL_EN))
		return 0;

	val &= ~USBPLL_WPLL_FREF_SEL;
	val |= USBPLL_WPLL_EN;
	writel(val, wpll->con1);
	udelay(20);

	val |= USBPLL_WPLL_SEL;
	writel(val, wpll->con1);

	val |= USBPLL_WPLL_AFC_START;
	writel(val, wpll->con1);
	usleep_range(60, 100);

	return 0;
}

static int exynos7570_wpll_is_prepared(struct clk_hw *hw)
{
	u32 val = readl(to_wpll(hw)->con1);

	return (val & (USBPLL_WPLL_SEL | USBPLL_WPLL_EN)) ==
	       (USBPLL_WPLL_SEL | USBPLL_WPLL_EN);
}

static unsigned long exynos7570_wpll_recalc_rate(struct clk_hw *hw,
						 unsigned long parent_rate)
{
	return USBPLL_RATE;
}

static const struct clk_ops exynos7570_wpll_ops = {
	.prepare	= exynos7570_wpll_prepare,
	.is_prepared	= exynos7570_wpll_is_prepared,
	.recalc_rate	= exynos7570_wpll_recalc_rate,
};

static void __init exynos7570_register_wpll(struct device *dev)
{
	static const char *const parents[] = { "oscclk" };
	struct clk_init_data init = {
		.name = "fout_fsys_wpll_usb",
		.ops = &exynos7570_wpll_ops,
		.parent_names = parents,
		.num_parents = 1,
	};
	struct exynos7570_wpll *wpll;
	void __iomem *base;

	base = of_iomap(dev->of_node, 0);
	if (!base) {
		dev_err(dev, "failed to map the CMU for the USB PLL\\n");
		return;
	}

	wpll = kzalloc(sizeof(*wpll), GFP_KERNEL);
	if (!wpll) {
		iounmap(base);
		return;
	}

	wpll->con1 = base + USBPLL_CON1_OFFSET;
	wpll->hw.init = &init;

	if (clk_hw_register(dev, &wpll->hw)) {
		dev_err(dev, "failed to register the USB PLL\\n");
		kfree(wpll);
		iounmap(base);
	}
}

static int __init exynos7570_cmu_probe(struct platform_device *pdev)
{
	const struct samsung_cmu_info *info;
	struct device *dev = &pdev->dev;

	info = of_device_get_match_data(dev);
	exynos_arm64_register_cmu(dev, dev->of_node, info);

	if (info == &fsys_cmu_info)
		exynos7570_register_wpll(dev);

	return 0;
}

static const struct of_device_id exynos7570_cmu_of_match[] = {''')
for cmu in order:
    out.append('\t{\n\t\t.compatible = "%s",\n\t\t.data = &%s_cmu_info,\n\t},' % (spec.CMUS[cmu]['compat'], cmu))
out.append('''	{ },
};

static struct platform_driver exynos7570_cmu_driver __refdata = {
	.driver = {
		.name = "exynos7570-cmu",
		.of_match_table = exynos7570_cmu_of_match,
		.suppress_bind_attrs = true,
	},
	.probe = exynos7570_cmu_probe,
};

static int __init exynos7570_cmu_init(void)
{
	return platform_driver_register(&exynos7570_cmu_driver);
}
core_initcall(exynos7570_cmu_init);
''')
open(os.path.join(LINUX, 'drivers/clk/samsung/clk-exynos7570.c'), 'w').write('\n'.join(out))
print('generated: %s' % ', '.join('%s=%d ids' % (c, nr[c] - 1) for c in nr))
