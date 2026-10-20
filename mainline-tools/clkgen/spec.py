# Which downstream (pwrcal S5E7570) clocks go into mainline clk-exynos7570.c.
# gen.py takes every offset/shift/width/parent from the downstream sources, so
# only the selection and the mainline names live here.
#
# entry: (kind, downstream name, mainline name or None for the automatic one, flags)
#   kind  : pll | mux | ffac | div | gate | frat
#   flags : gate only - 'rate' = CLK_SET_RATE_PARENT, 'crit' = CLK_IS_CRITICAL

CMUS = {
    'mif':  dict(base=0x10460000, compat='samsung,exynos7570-cmu-mif'),
    'fsys': dict(base=0x13730000, compat='samsung,exynos7570-cmu-fsys'),
    'peri': dict(base=0x101f0000, compat='samsung,exynos7570-cmu-peri'),
    'dispaud': dict(base=0x148d0000, compat='samsung,exynos7570-cmu-dispaud'),
}

EXTERNAL = {
    'OSCCLK': 'oscclk',
    # registered by hand in clk-exynos7570.c (AP-owned WPLL, see there)
    'WIFI2AP_USBPLL_CLK': 'fout_fsys_wpll_usb',
}

# Downstream parents that are modelled by another clock here. WPLL_USB_PLL is
# the 20 MHz USB PLL; it is implemented as a hand-written clock in the driver.
ALIASES = {'WPLL_USB_PLL': 'WIFI2AP_USBPLL_CLK'}

MIF_CMU_CLOCKS = [          # CLKCMU_<x>: mux -> div -> gate towards other CMUs
    'FSYS_BUS', 'FSYS_MMC0', 'FSYS_MMC2', 'FSYS_USB20DRD_REFCLK',
    'PERI_BUS', 'PERI_UART_DEBUG', 'PERI_UART_SENSOR',
    'PERI_SPI_REARFROM', 'PERI_SPI_ESE', 'PERI_USI_0', 'PERI_USI_1',
    'DISPAUD_BUS', 'DISPAUD_DECON_INT_VCLK',
]

SPEC = {'mif': [], 'fsys': [], 'peri': [], 'dispaud': []}

m = SPEC['mif']
for n in (0, 1, 2):
    m.append(('pll', 'SHARED%d_PLL' % n, None, ''))
for n in (0, 1, 2):
    m.append(('mux', 'MIF_MUX_SHARED%d_PLL' % n, None, ''))
for n in (0, 1, 2):
    m.append(('ffac', 'MIF_FF_SHARED%d_PLL_DIV2' % n, None, ''))
m.append(('frat', 'TCXO', 'frat_mif_tcxo', ''))
m.append(('mux', 'MIF_MUX_CLK_MIF_BUSD', 'mout_mif_busd', ''))
m.append(('div', 'MIF_DIV_CLK_MIF_BUSD', 'dout_mif_busd', ''))
m.append(('div', 'MIF_DIV_CLK_MIF_APB', 'dout_mif_apb', ''))
for x in MIF_CMU_CLOCKS:
    m.append(('mux', 'MIF_MUX_CLKCMU_' + x, None, ''))
    m.append(('div', 'MIF_DIV_CLKCMU_' + x, None, ''))
    m.append(('gate', 'MIF_GATE_CLKCMU_' + x, None, 'rate'))
m += [
    ('gate', 'MIF_GATE_CLK_MIF_UID_PDMA_MIF_IPCLKPORT_ACLK_PDMA0', 'gout_mif_pdma0_aclk', 'rate'),
    ('gate', 'MIF_GATE_CLK_MIF_UID_SPEEDY_MIF_IPCLKPORT_PCLK', 'gout_mif_speedy_pclk', 'rate'),
    ('gate', 'MIF_GATE_CLK_MIF_UID_SPEEDY_MIF_IPCLKPORT_CLK', 'gout_mif_speedy_clk', 'rate'),
    ('gate', 'MIF_GATE_CLK_MIF_UID_WRAP_ADC_IF_IPCLKPORT_PCLK_S0', 'gout_mif_adc_pclk_s0', 'rate'),
    ('gate', 'MIF_GATE_CLK_MIF_UID_WRAP_ADC_IF_IPCLKPORT_PCLK_S1', 'gout_mif_adc_pclk_s1', 'crit'),
    ('gate', 'MIF_GATE_CLK_MIF_UID_WRAP_ADC_IF_IPCLKPORT_I_OSC_SYS', 'gout_mif_adc_osc_sys', ''),
    ('gate', 'MIF_GATE_CLK_MIF_UID_GPIO_MIF_IPCLKPORT_PCLK', 'gout_mif_gpio_pclk', 'crit'),
    ('gate', 'MIF_GATE_CLK_MIF_UID_SYSREG_MIF_IPCLKPORT_PCLK', 'gout_mif_sysreg_pclk', 'crit'),
]

f = SPEC['fsys']
f += [
    ('frat', 'CLKPHY_FSYS_USB20DRD_PHYCLOCK', 'frat_fsys_usb20drd_phyclock', ''),
    ('mux', 'FSYS_MUX_CLKPHY_FSYS_USB20DRD_PHYCLOCK_USER', 'mout_fsys_usb20drd_phyclock_user', ''),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_MMC_EMBD_IPCLKPORT_I_ACLK', 'gout_fsys_mmc_embd_aclk', 'rate'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_MMC_CARD_IPCLKPORT_I_ACLK', 'gout_fsys_mmc_card_aclk', 'rate'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_MMC_EMBD_IPCLKPORT_SDCLKIN', 'gout_fsys_mmc_embd_sdclkin', 'rate'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_MMC_CARD_IPCLKPORT_SDCLKIN', 'gout_fsys_mmc_card_sdclkin', 'rate'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_USB20DRD_IPCLKPORT_HCLK_USB20_CTRL', 'gout_fsys_usb20drd_hclk_ctrl', 'rate'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_USB20DRD_IPCLKPORT_ACLK_HSDRD', 'gout_fsys_usb20drd_aclk_hsdrd', 'rate'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_USB20DRD_IPCLKPORT_HSDRD_ref_clk', 'gout_fsys_usb20drd_ref_clk', 'rate'),
    # the PHY driver only enables its "phy" clock around the init; the controller needs it running
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_USB20DRD_IPCLKPORT_HSDRD_PHYCLOCK', 'gout_fsys_usb20drd_phyclock', 'crit'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_USB20DRD_IPCLKPORT_USB20_CLKCORE_0', 'gout_fsys_usb20drd_clkcore', 'rate'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_GPIO_FSYS_IPCLKPORT_PCLK', 'gout_fsys_gpio_pclk', 'crit'),
    ('gate', 'FSYS_GATE_CLK_FSYS_UID_SYSREG_FSYS_IPCLKPORT_PCLK', 'gout_fsys_sysreg_pclk', 'crit'),
]

p = SPEC['peri']
p += [
    ('div', 'PERI_DIV_CLK_PERI_USI_0_SPI', 'dout_peri_usi0_spi', ''),
    ('div', 'PERI_DIV_CLK_PERI_USI_1_SPI', 'dout_peri_usi1_spi', ''),
]
for ds, name, fl in [
    ('UART_DEBUG_IPCLKPORT_PCLK', 'gout_peri_uart_debug_pclk', 'rate'),
    ('UART_DEBUG_IPCLKPORT_EXT_UCLK', 'gout_peri_uart_debug_uclk', 'rate'),
    ('UART_SENSOR_IPCLKPORT_PCLK', 'gout_peri_uart_sensor_pclk', 'rate'),
    ('UART_SENSOR_IPCLKPORT_EXT_UCLK', 'gout_peri_uart_sensor_uclk', 'rate'),
    ('USI_0_IPCLKPORT_i_PCLK', 'gout_peri_usi0_pclk', 'rate'),
    ('USI_0_IPCLKPORT_i_SCLK_UART', 'gout_peri_usi0_sclk_uart', 'rate'),
    ('USI_0_IPCLKPORT_i_SCLK_SPI', 'gout_peri_usi0_sclk_spi', 'rate'),
    ('USI_1_IPCLKPORT_i_PCLK', 'gout_peri_usi1_pclk', 'rate'),
    ('USI_1_IPCLKPORT_i_SCLK_UART', 'gout_peri_usi1_sclk_uart', 'rate'),
    ('USI_1_IPCLKPORT_i_SCLK_SPI', 'gout_peri_usi1_sclk_spi', 'rate'),
    ('SPI_ESE_IPCLKPORT_PCLK', 'gout_peri_spi_ese_pclk', 'rate'),
    ('SPI_ESE_IPCLKPORT_SPI_EXT_CLK', 'gout_peri_spi_ese_clk', 'rate'),
    ('SPI_REARFROM_IPCLKPORT_PCLK', 'gout_peri_spi_rearfrom_pclk', 'rate'),
    ('SPI_REARFROM_IPCLKPORT_SPI_EXT_CLK', 'gout_peri_spi_rearfrom_clk', 'rate'),
    ('MCT_IPCLKPORT_PCLK', 'gout_peri_mct_pclk', 'rate'),
    ('WDT_CPUCL0_IPCLKPORT_PCLK', 'gout_peri_wdt_cpucl0_pclk', 'rate'),
    ('I2C_SENSOR1_IPCLKPORT_PCLK', 'gout_peri_i2c_sensor1_pclk', 'rate'),
    ('I2C_SENSOR2_IPCLKPORT_PCLK', 'gout_peri_i2c_sensor2_pclk', 'rate'),
    ('I2C_TSP_IPCLKPORT_PCLK', 'gout_peri_i2c_tsp_pclk', 'rate'),
    ('I2C_FUELGAUGE_IPCLKPORT_PCLK', 'gout_peri_i2c_fuelgauge_pclk', 'rate'),
    ('I2C_NFC_IPCLKPORT_PCLK', 'gout_peri_i2c_nfc_pclk', 'rate'),
    ('I2C_MUIC_IPCLKPORT_PCLK', 'gout_peri_i2c_muic_pclk', 'rate'),
    ('HSI2C_FRONTCAM_IPCLKPORT_iPCLK', 'gout_peri_hsi2c_frontcam_pclk', 'rate'),
    ('HSI2C_MAINCAM_IPCLKPORT_iPCLK', 'gout_peri_hsi2c_maincam_pclk', 'rate'),
    ('HSI2C_FRONTSENSOR_IPCLKPORT_iPCLK', 'gout_peri_hsi2c_frontsensor_pclk', 'rate'),
    ('HSI2C_REARAF_IPCLKPORT_iPCLK', 'gout_peri_hsi2c_rearaf_pclk', 'rate'),
    ('HSI2C_REARSENSOR_IPCLKPORT_iPCLK', 'gout_peri_hsi2c_rearsensor_pclk', 'rate'),
    ('PWM_MOTOR_IPCLKPORT_i_PCLK_S0', 'gout_peri_pwm_motor_pclk', 'rate'),
    ('SFRIF_RTC_ALIVE_IPCLKPORT_PCLK', 'gout_peri_rtc_alive_pclk', 'rate'),
    ('SFRIF_RTC_TOP_IPCLKPORT_PCLK', 'gout_peri_rtc_top_pclk', 'rate'),
    ('SFRIF_CHIPID_IPCLKPORT_PCLK', 'gout_peri_chipid_pclk', 'rate'),
    ('GPIO_TOUCH_IPCLKPORT_PCLK', 'gout_peri_gpio_touch_pclk', 'crit'),
    ('GPIO_TOP_IPCLKPORT_PCLK', 'gout_peri_gpio_top_pclk', 'crit'),
    ('GPIO_NFC_IPCLKPORT_PCLK', 'gout_peri_gpio_nfc_pclk', 'crit'),
    ('GPIO_ESE_IPCLKPORT_PCLK', 'gout_peri_gpio_ese_pclk', 'crit'),
    ('SFRIF_GPIO_ALIVE_IPCLKPORT_PCLK', 'gout_peri_gpio_alive_pclk', 'crit'),
    ('SYSREG_PERI_IPCLKPORT_PCLK', 'gout_peri_sysreg_pclk', 'crit'),
]:
    p.append(('gate', 'PERI_GATE_CLK_PERI_UID_' + ds, name, fl))

# CMU_DISPAUD (0x148D0000): display (the 7870-style ECLK_USER mux at +0x218 faults on 7570, left out) (and audio+MI2S, excluded here). The DECON
# ECLK user mux has no MIF-side divider of its own on the 7570 - pwrcal feeds
# it from the MIF CLKCMU_DISPAUD_DECON_INT_VCLK gate. frats are the same
# 188 MHz placeholders upstream 7870 uses (nothing reads the byte/esc rate).
d = SPEC['dispaud'] = [
    ('frat', 'CLKPHY_DISPAUD_MIPIPHY_TXBYTECLKHS', 'frat_dispaud_mipiphy_txbyteclkhs', ''),
    ('frat', 'CLKPHY_DISPAUD_MIPIPHY_RXCLKESC0', 'frat_dispaud_mipiphy_rxclkesc0', ''),
    ('mux', 'DISPAUD_MUX_CLKCMU_DISPAUD_BUS_USER', 'mout_dispaud_bus_user', ''),
    ('mux', 'DISPAUD_MUX_CLKCMU_DISPAUD_DECON_INT_VCLK_USER', 'mout_dispaud_decon_vclk_user', ''),
    ('mux', 'DISPAUD_MUX_CLKPHY_DISPAUD_MIPIPHY_TXBYTECLKHS_USER', 'mout_dispaud_mipiphy_txbyteclkhs_user', ''),
    ('mux', 'DISPAUD_MUX_CLKPHY_DISPAUD_MIPIPHY_RXCLKESC0_USER', 'mout_dispaud_mipiphy_rxclkesc0_user', ''),
    ('div', 'DISPAUD_DIV_CLK_DISPAUD_APB', 'dout_dispaud_apb', ''),
    ('div', 'DISPAUD_DIV_CLK_DISPAUD_DECON_INT_VCLK', 'dout_dispaud_decon_vclk', ''),
]
# The bus and APB gates are critical: the display runs on them from the
# bootloader on, and their other users (the SysMMU) would otherwise gate it by
# enabling and disabling them while probing.
# CLK_ENABLE_CLK_DISPAUD_BUS/APB/DECON_INT_VCLK/MIPIPHY gates. On the 7570 the
# DECON I_VCLK gate (0x820) is the only internal decon gate; there is no
# separate ECLK gate, and the mipiphy gates are 0x824/0x828.
for ds, name, fl in [
    ('DISPAUD_GATE_CLK_DISPAUD_UID_CLKCMU_DISPAUD_BUS', 'gout_dispaud_bus', 'crit'),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_CLKCMU_DISPAUD_BUS_VPP', 'gout_dispaud_bus_vpp', ''),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_CLKCMU_DISPAUD_BUS_DISP', 'gout_dispaud_bus_disp', 'crit'),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_CLKCMU_DISPAUD_BUS_PPMU', 'gout_dispaud_bus_ppmu', ''),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_CLK_DISPAUD_APB', 'gout_dispaud_apb', 'crit'),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_CLK_DISPAUD_APB_DISP', 'gout_dispaud_apb_disp', 'crit'),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_DECON_IPCLKPORT_I_VCLK', 'gout_dispaud_decon_vclk', ''),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_DSIM0_IPCLKPORT_I_TXBYTECLKHS', 'gout_dispaud_mipiphy_txbyteclkhs', ''),
    ('DISPAUD_GATE_CLK_DISPAUD_UID_DSIM0_IPCLKPORT_I_RXCLKESC0', 'gout_dispaud_mipiphy_rxclkesc0', ''),
]:
    d.append(('gate', ds, name, fl))
