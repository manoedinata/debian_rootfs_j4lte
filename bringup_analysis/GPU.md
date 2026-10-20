# GPU bring-up analysis — Mali-T720 on mainline (Exynos7570, Galaxy J4)

**Status (2026-10-20, later): working.** Panfrost probes (`mali-t720 id 0x720`, one
shader core) at a fixed 349.4 MHz, and Phosh renders on it smoothly. Commits:
07600c011 (CMU_G3D), 46f32b6c2 (binding), 662c949bd (DT); outer repo 34eb68d, dbd5f77.
The bootloader leaves G3D powered with every gate on, MIF CLKCMU_G3D = SHARED2 (mux 2,
div 1), G3D_BUS div /4, APB /4. Left: Phosh device path (Panfrost is card0, the display
card1), OPP/devfreq, thermal.

Original analysis (2026-10-20): Sources: downstream 3.18 tree
(`kernel/`), mainline tree (`linux-7.2.y/`), and read-only checks on the running
mainline phone. Unverified points are marked **(unverified)**.

## Summary

The GPU looks like one of the easier blocks to bring up. Panfrost already supports the
T720, the phone's Mesa ships `panfrost_dri.so` and the `exynos_dri.so` kmsro pairing, and
the voltage rail is already above the GPU's highest operating point. Work needed:

1. Clocks: `CLKCMU_G3D` in CMU_MIF and a new CMU_G3D (0x11460000) via clkgen.
2. Power domain: `pd_g3d` at PMU 0x11c84000 (`samsung,exynos5433-pd`, like `pd_dispaud`).
3. DT: a `gpu@11400000` node with `arm,mali-t720` and an Exynos7570 compatible, plus a
   binding update.
4. Config: `CONFIG_DRM_PANFROST`.
5. Userspace: test with `kmscube` / `eglinfo`, then Phosh with the software renderer
   override removed.

DVFS (devfreq + OPP + regulator) can come later; the first bring-up can run at a fixed
clock.

## Hardware facts (from downstream)

### GPU node (`kernel/arch/arm64/boot/dts/exynos7570-rev01.dtsi:1007`)

```
mali: mali@11400000 {
	compatible = "arm,mali";
	reg = <0x0 0x11400000 0x5000>;
	interrupts = <0 282 0>, <0 283 0>, <0 281 0>;
	interrupt-names = "JOB", "MMU", "GPU";
	clocks = <&clock 203>;          /* vclk_g3d = pwrcal dvfs_g3d */
	clock-names = "vclk_g3d";
	samsung,power-domain = <&pd_g3d>;
};
```

- Registers 0x11400000, size 0x5000 (Midgard register space fits in 0x4000).
- IRQs: SPI 282 = job, SPI 283 = mmu, SPI 281 = gpu. Panfrost wants the names
  `job`, `mmu`, `gpu` (lowercase), so the mapping is direct.
- The trigger type in downstream is 0 (none given). Mainline should use
  `IRQ_TYPE_LEVEL_HIGH` like the other 7570 SPIs **(unverified for these three)**.

### Power domain (`exynos7570-pm-domains.dtsi:52`)

```
pd_g3d: pd-g3d@11C84000 { compatible = "samsung,exynos-pd"; reg = <0x0 0x11C84000 0x20>; }
```

Same PMU layout as DISPAUD (0x11c84020), which already works in mainline as
`samsung,exynos5433-pd`. So `pd_g3d` should be a plain node at 0x11c84000.

### Clocks (`pwrcal/S5E7570/S5E7570-cmu.c`, `-cmusfr.h`, `-dfs.c`)

Clock chain: `MIF_MUX_CLKCMU_G3D` (parents SHARED0/1/2_PLL) → `MIF_DIV_CLKCMU_G3D` (4 bit) →
`MIF_GATE_CLKCMU_G3D` → CMU_G3D `MUX_CLKCMU_G3D_USER` (oscclk | CLKCMU_G3D) →
`DIV_CLK_G3D_BUS` (3 bit, 0x400) → `DIV_CLK_G3D_APB` (3 bit, 0x404).

CMU_G3D (base 0x11460000) registers:

| Reg | Offset | Contents |
|---|---|---|
| CLK_CON_MUX_CLKCMU_G3D_USER | 0x204 | select bit 12 |
| CLK_CON_DIV_CLK_G3D_BUS | 0x400 | div bits 0..2 |
| CLK_CON_DIV_CLK_G3D_APB | 0x404 | div bits 0..2 |
| CLK_STAT_MUX_CLKCMU_G3D_USER | 0x604 | |
| CLK_ENABLE_CLK_G3D_OSCCLK | 0x800 | bit0 PMU_G3D, bit1 SYSREG_G3D |
| CLK_ENABLE_CLK_G3D_BUS | 0x804 | bit6 = **G3D core clock**, others are bus/async/QE/PPMU |
| CLK_ENABLE_CLK_G3D_APB | 0x808 | APB gates (sysreg, QE, PPMU, PMU, BUSP, async) |

The secure CFW gates (`CLK_ENABLE_CLK_G3D_*_SECURE_CFW_G3D`) must not be touched.

Downstream groups the gates the GPU needs as `gategrp_g3d_g3d` (`S5E7570-vclk.c`):
`G3D_IPCLKPORT_CLK` (BUS bit6), `ASYNCS_D0` (BUS bit1), `ASYNC_G3D_P_PCLKM` (BUS bit0) and
`SYSREG_G3D_PCLK` (APB bit6). Lesson from DISPAUD: shared bus/APB gates should probably be
`CLK_IS_CRITICAL`, or held by one owner, so nothing gates them by toggling.

The clkgen generator (`mainline-tools/clkgen/spec.py`) has no G3D yet. Needed:
`'G3D'` in `MIF_CMU_CLOCKS` (adds mux/div/gate) and a new `SPEC['g3d']` section. Adding
ids renumbers the binding header, so regenerate everything and check the diff, as before.

**Rule from the port:** never read undefined CMU offsets (the FSYS+0x810 hole stalled the
bus; DISPAUD+0x218 aborted). Only list registers that exist in pwrcal.

### Frequencies (`r29p0/platform/exynos/gpu_exynos7570.c:77`)

| MHz | mV (table) | Likely source (SHARED0/1/2 = 1657.5/1332.5/1397.5 MHz) |
|---|---|---|
| 830 | 900 | SHARED0 / 2 = 828.75 |
| 666 | 900 | SHARED1 / 2 = 666.25 |
| 553 | 900 | SHARED0 / 3 = 552.5 |
| 415 | 900 | SHARED0 / 4 = 414.4 |
| 350 | 850 | SHARED2 / 4 = 349.4 |

The real rate list and voltages come from the bootloader's ECT blob (`ect_get_block("DVFS")`
in `S5E7570-dfs.c`) plus per-chip ASV tables, so the table above is nominal. The
parent/divider mapping is my inference from the PLL rates **(unverified)**.

### Supply

- The GPU runs from **BUCK1** (`gpu_regulator_init()`: `regulator_get(dev, "BUCK1")`).
- BUCK1 is **shared with the CPU cluster** (`cl0_regulator = "BUCK1"` in
  `exynos7570-rev01.dtsi:148`). Any GPU voltage scaling must not drop the CPU's voltage;
  the regulator framework's range voting handles that if both are consumers.
- On the running mainline kernel, BUCK1 reads **925 mV**, above the table maximum of
  900 mV. So a fixed-clock first bring-up needs no voltage control. Mainline marks BUCK1
  `regulator-always-on`.

## Mainline status (linux-7.2.y)

- Panfrost knows the T720: `GPU_MODEL(t720, 0x720)` in `panfrost_gpu.c`, `hw_issues_t720`
  and `hw_features_t720` exist, and `arm,mali-t720` is in the match table (`default_data`).
- `default_data` expects one clock (and optionally `bus`), the `mali` supply (optional),
  and a power domain. Check `panfrost_drv.c` for the exact names before writing the DT.
- Binding `arm,mali-midgard.yaml`: T720 only allows `allwinner,sun50i-h6-mali`. Add
  `samsung,exynos7570-mali` to that enum.
- The 7570 DT has no `pd_g3d`, no CMU_G3D and no GPU node.
- Thermal: there is no TMU driver for the 7570 in mainline, so there is no throttling. A
  fixed moderate clock (350–415 MHz) is the safe choice until thermal exists.

## Userspace (Debian 11 on p25)

- Mesa 20.3.5 (`libgl1-mesa-dri`, `libegl-mesa0`); `panfrost_dri.so` and `exynos_dri.so`
  are installed. `exynos_dri.so` is the kmsro loader that pairs the exynos display
  (card0) with the Panfrost render node.
- Mesa 20.3 Panfrost on the T720 should give GLES 2.0 (Midgard v4), which is enough for
  wlroots/phoc **(unverified on this phone)**. A newer Mesa (bookworm/backports) would be
  better if 20.3 has T720 bugs.
- After it works: drop `WLR_RENDERER_ALLOW_SOFTWARE=1`.

## Proposed plan

1. **Read-only check of the bootloader state:** read CMU_MIF CLKCMU_G3D mux/div, CMU_G3D
   0x204/0x400/0x404/0x800–0x808, and PMU 0x11c84000/0x11c84004. These are only offsets
   known from pwrcal; the read is done from downstream with `regpeek`. It shows what
   S-BOOT leaves on and at what rate.
2. **Clocks:** extend clkgen (MIF `CLKCMU_G3D` plus CMU_G3D), regenerate, commit.
3. **Power domain:** add `pd_g3d` and attach CMU_G3D to it (`power-domains`), as with
   DISPAUD.
4. **GPU node:** add `gpu@11400000`, compatible `"samsung,exynos7570-mali", "arm,mali-t720"`,
   IRQs 282/283/281 named job/mmu/gpu, clock = the G3D core gate, `power-domains = <&pd_g3d>`,
   and `assigned-clock-rates` at about 415 MHz. Update the binding.
5. **Config:** `CONFIG_DRM_PANFROST=y` (edit `.config` plus olddefconfig, never a defconfig).
6. **Test:** check the boot log for `panfrost ... mali-t720 id 0x720` and a
   `/dev/dri/renderD128`. Then run `eglinfo` / `kmscube` (install with approval), then
   Phosh without the software renderer.
7. **Later:** OPP table + devfreq (`mali-supply = <&buck1_reg>`, needs CPU rail
   coordination), thermal (a TMU driver), and runtime PM / power domain off at idle.

## Risks / open questions

- The parent/divider choice for each rate is inferred; verify it against the registers in
  step 1.
- Which gate is the "core" clock for Panfrost vs. which must merely stay on; probably the
  G3D_IPCLKPORT_CLK gate as the main clock and the bus/APB gates critical.
- Power-domain off/on for G3D has never been exercised on mainline; DISPAUD's domain was
  left on. Keep the domain on at first if it misbehaves.
- No thermal protection on mainline: avoid long high-clock loads.
- The data-corruption bug seen with large apt runs might affect GPU testing; keep an eye
  on unexplained failures.
- A G3D SysMMU exists in pwrcal gate groups, but Midgard uses its own MMU, so it should
  not be needed **(unverified)**.
