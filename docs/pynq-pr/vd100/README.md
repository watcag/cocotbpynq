# Alinx VD100 (Versal AI Edge)

pynq-pr builds DFX designs for the Alinx VD100 (`xcve2302-sfva784-1LP-e-s`) with Vivado 2025.1, from the
same YAML as the Z1 and KV260:

```sh
cd examples/pynq-pr/add_sub
pynq-pr build -c pr_vd100.yaml        # vivado 2025.1 on PATH
```

## What is different on Versal

| | Z1 / KV260 | VD100 |
|---|---|---|
| Images | `.bit` | `.pdi` (programmable device image) |
| Static image | loaded at runtime | **boots with the board** (in `BOOT.BIN`) |
| Partial loading | PCAP or ICAP | the platform loader (PLM), commanded from Python |
| PS-PL data path | HP0 port | NoC port into the DDR4 controller |
| Board definition | Vivado board file | `scripts/ps_vd100.tcl` (CIPS, NoC, DDR4), `constraints/vd100.xdc` (pins) |
| Partitions | 1–4 | 1–3, from the board's layouts |

On Gen 1 Versal devices such as the VE2302, Linux cannot reload the whole PL of a DFX design (that needs
segmented configuration with DFX, Gen 2 only:
[UG909](https://docs.amd.com/r/en-US/ug909-vivado-partial-reconfiguration/Segmented-Configuration-and-DFX)).
So the static design boots with the board, and changing it means a new `BOOT.BIN` and a reboot; changing
a module does not.

`bits/` holds `<project>.pdi` (the full design, for `BOOT.BIN`), one uncompressed partial
`<partition>_<cell_name>.pdi` per module, and their `.hwh` files.

## Boot image

`BOOT.BIN` is the static PDI plus the A72 software of the board's PYNQ image (device tree, BL31, U-Boot,
built with the same Vivado release). With bootgen from Vivado 2025.1:

```
the_ROM_image:
{
    image {
        { type=bootimage, file=<project>.pdi }
    }
    image {
        name=apu_subsystem
        id=0x1c000000
        { type=raw, load=0x00001000, file=system.dtb }
        { core=a72-0, exception_level=el-3, trustzone, file=bl31.elf }
        { core=a72-0, exception_level=el-2, file=u-boot.elf }
    }
}
```

```sh
bootgen -arch versal -image boot.bif -o BOOT.BIN -w
```

`ps_vd100.tcl` matches the board's factory CIPS preset, so the image's kernel and device tree boot with
any pynq-pr static design. It pins the CIPS and NoC IP versions of Vivado 2025.1.

## Floorplan

All DSPs are in clock-region column X2 and all PL NoC endpoints in column X1, so the board lists its
layouts (`boards.py`) instead of leaving the split to the floorplanner. Every partition is whole clock
regions and has DSPs:

| Partitions | Partitions' clock regions | Static |
|---|---|---|
| 1 | rows Y2 + Y3 | X1Y1, X2Y1 |
| 2 | row Y2; row Y3 | X1Y1, X2Y1 |
| 3 | row Y2; row Y3; X2Y1 | X1Y1 |

## NoC interconnect

`noc_interconnect: true` routes the partitions' streams over the NoC instead of the AXI4-Stream switch
(`examples/pynq-pr/vision/pr_vd100_noc.yaml`). Modules, DMAs, decouplers and AXI-Lite control stay as
they are.

- Endpoint 2i is partition i and 2i+1 is DMA i, as on the switch. Every source enters the NoC at a static
  NMU, tagged with its destination from the `rps_route` GPIO (`NocRoute` in the runtime); each partition's
  input is an NSU inside the partition, which the PLM quiesces during reconfiguration. A route change
  applies from the next packet.
- Vivado requires this shape: a path between partitions must belong to a static NoC instance, and only
  static NMUs can fan out by destination (UG909's "NMU static, NSU dynamic" topology).
- It needs 2N + 1 NMUs and 2N NSUs. The VE2302 has five of each, so it takes 1–2 partitions;
  `pynq-pr validate` checks the budget.

## Runtime

```python
ol = Overlay("tutorial_vd100.pdi")      # attaches to the design that booted
ol.pr_download("add", "add_c_5.pdi")     # decouple, load, recouple
```

The overlay sends the PLM its load command over IPI channel 3 (`pynq_pr.overlay.Plm`, Versal Gen 1), and
the PLM loads the partial from DDR. Each partial is copied into a DMA buffer on its first load and stays
there. When it opens, the overlay checks that the PLM answers on the channel and turns off the PLM's
console output until reboot (`Plm().enable_uart()` restores it): the PLM waits for every line it prints
at 115200 baud, about 46 ms per load.

- IPI channel 3 must belong to the A72 cores (`ps_vd100.tcl`) and be unused by other software. One
  process at a time owns it.
- Load only through `pr_download`: accessing a partition that is being loaded without decoupling hangs
  the board. A failed load leaves the partition decoupled until a later load succeeds.
- Partials are uncompressed because the PLM writes raw frames faster than it decompresses them.

Load times (`add_sub`, median of 50):

| Partial | Size | Load |
|---|---|---|
| `add`: a row of 3 clock regions | 9.0 MB | 3.8 ms |
| `mult`: 1 clock region | 3.4 MB | 2.6 ms |
