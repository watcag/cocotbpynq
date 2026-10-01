# KV260 Custom PMU Firmware for ICAPE3 Partial Reconfiguration

On the KV260 (K26 SOM), the default PMU firmware blocks the CSU register writes
needed to hand off configuration control from PCAP to ICAP. This means partial
reconfiguration via ICAPE3 silently fails even though the initial full bitstream
loads fine via PCAP.

The fix is a custom PMU firmware compiled with `SECURE_ACCESS_VAL=1`, which
unlocks access to the CSU registers that gate PCAP/ICAP control. A pre-built
`BOOT.BIN` with this fix is included in this directory.

Check the file before flashing it:

```bash
sha256sum docs/pynq-pr/kv260/BOOT.BIN
# a02cec2e8ddf8767db0d7333ddda8550c8efd85aa4b64d63c2cc7ff35e8e8ff5
```

It was built with the recipe in [Rebuild from source](#rebuild-from-source)
(PetaLinux/BSP version: TODO). You only need it for `reconfiguration_method: icap`
on the KV260; PCAP works with the stock firmware.

## Diagnose

To confirm this is the issue, log into the board and run as root:

```bash
sudo su
echo 0xffca3008 > /sys/firmware/zynqmp/config_reg
cat /sys/firmware/zynqmp/config_reg
```

If the output is `Permission denied`, the PMU firmware is blocking CSU register
access and ICAP will not work. Apply the fix below.

If you get a hex value back, CSU access is already enabled and this is not your
issue.

## Flash the pre-built BOOT.BIN

**1. Copy BOOT.BIN to the board:**

```bash
scp docs/pynq-pr/kv260/BOOT.BIN ubuntu@<board-ip>:/tmp/BOOT.BIN
```

**2. Flash to the non-active QSPI slot:**

```bash
# On the KV260
sudo xmutil bootfw_update -i /tmp/BOOT.BIN
```

**3. Reboot:**

```bash
sudo reboot
```

**4. Validate the new firmware is active:**

```bash
sudo xmutil bootfw_update -v
```

If validation succeeds, partial reconfiguration via ICAPE3 should now work. If
you reboot again without validating, the board reverts to the previous firmware.

---

## Rebuild from source

Use this if you need a different PetaLinux version or BSP.

**1. Create a PetaLinux project from the KV260 BSP:**

```bash
petalinux-create -t project -s xilinx-kv260-starterkit-v<version>.bsp
cd <project-dir>
```

**2. Enable `SECURE_ACCESS_VAL` in the PMU firmware:**

Create or edit `project-spec/meta-user/recipes-bsp/embeddedsw/pmu-firmware_%.bbappend`:

```
YAML_COMPILER_FLAGS:append = " -DSECURE_ACCESS_VAL=1"
```

**3. Build and package:**

```bash
petalinux-build
petalinux-package --boot \
    --fsbl images/linux/zynqmp_fsbl.elf \
    --pmufw images/linux/pmufw.elf \
    --u-boot images/linux/u-boot.elf \
    --atf images/linux/bl31.elf \
    --force
```

The output is `images/linux/BOOT.BIN`. Flash it using the steps above.
