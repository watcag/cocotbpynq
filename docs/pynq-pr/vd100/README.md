# Alinx VD100 (Versal AI Edge)

pynq-pr builds DFX designs for the Alinx VD100 (`xcve2302-sfva784-1LP-e-s`) with Vivado 2025.1, from the
same YAML as the Z1 and KV260:

```sh
cd examples/pynq-pr/add_sub
pynq-pr build -c pr_vd100.yaml        # vivado 2025.1 on PATH
```

The builds are checked ([Checked](#checked-vivado-20251-no-board)); they have not yet run on the board.
This page says what differs from the Zynq boards, how the outputs reach the board,
and what is still to be measured.

## What is different on Versal

| | Z1 / KV260 | VD100 |
|---|---|---|
| Images | `.bit` | `.pdi` (programmable device image) |
| Static image | loaded at runtime (`Overlay("x.bit")`) | **boots with the board** (in `BOOT.BIN`) |
| Partial loading | PCAP (fpga_manager) or ICAP (VERSATILE) | the PMC's platform loader (PLM), through the Linux FPGA manager |
| `reconfiguration_method` | `pcap`, `icap` | `pcap` only: Versal has no ICAP |
| PS-PL data path | HP0 port | NoC port into the DDR4 controller |
| Board definition | Vivado board file | `ps_vd100.tcl` (CIPS, NoC, DDR4) and `constraints/vd100.xdc` (pins) |
| Partitions | 1–4, split by the floorplanner | 1–3, from the board's layouts |

**Why the static image boots with the board.** Versal reloads the whole PL from Linux only with
*segmented configuration*, which splits a design into a boot PDI (PS, NoC, DDR) and a PL PDI. Combining
segmented configuration with DFX needs Vivado 2026.1 and a Versal Gen 2 device
([UG909](https://docs.amd.com/r/en-US/ug909-vivado-partial-reconfiguration/Segmented-Configuration-and-DFX));
the VE2302 is Gen 1. So a DFX design is one full PDI, loaded by the PLM at boot, and Linux loads only its
partial PDIs. Changing the static design means a new `BOOT.BIN` and a reboot; changing a module does not.

## Outputs

`output/<project>/bits/`:

| File | What it is |
|---|---|
| `<project>.pdi` | the full design (PLM, PS, NoC, DDR, static PL, first module of every partition): goes into `BOOT.BIN` |
| `<project>.hwh` | its hardware handoff |
| `<partition>_<cell_name>.pdi` | one partial PDI per module |
| `<partition>_<cell_name>.hwh` | its hardware handoff |

## Boot image

`BOOT.BIN` is the static PDI plus the A72 software of the board's boot set (BL31, U-Boot and device tree
from the board's PYNQ image, built with the same Vivado release). With bootgen from Vivado 2025.1:

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

`ps_vd100.tcl` configures the CIPS exactly as the boot set's device tree expects (the effective CIPS
configuration equals the board's factory preset with the PYNQ PL interface), so the same kernel and device
tree boot with any pynq-pr static design. The script pins the CIPS and NoC IP versions of Vivado
2025.1, so another release fails at the block design until the configuration is checked against it.

## Floorplan

The VE2302 has eight fabric clock regions, and they differ in kind:

```
          X0                 X1                        X2
Y3   9.9k LUT          14.1k LUT, 1 NoC pair      11.3k LUT,  88 DSP     (half-height row)
Y2  21.5k LUT          30.7k LUT, 2 NoC pairs     24.6k LUT, 192 DSP
Y1  (PS side of NoC)   14.7k LUT, 2 NoC pairs     23.6k LUT, 184 DSP
```

All DSPs are in column X2, and all PL NoC endpoints (NMU512/NSU512 pairs) in column X1. A path-splitting
floorplanner would give partitions without DSPs, so the board lists its layouts (`boards.py`):

| Partitions | Partitions' clock regions | Static |
|---|---|---|
| 1 | rows Y2 + Y3 | X1Y1, X2Y1 |
| 2 | row Y2; row Y3 | X1Y1, X2Y1 |
| 3 | row Y2; row Y3; X2Y1 | X1Y1 |

Every partition is whole clock regions (no DRCs from shared clock regions) and every one has DSPs.
X1Y1 stays static in every layout, with the static DMAs and their NoC port (`ps_vd100.tcl`).

## NoC interconnect

`noc_interconnect: true` routes the partitions' streams over the NoC instead of the AXI4-Stream
switch (`examples/pynq-pr/vision/pr_vd100_noc.yaml`). Everything else stays: each partition keeps its
DMA, decoupler and AXI-Lite control, and the module RTL keeps its 32-bit `x`/`y` streams.

```
 DMA i MM2S ──tag──► NMU ┐                ┌─► NSU ──► DMA i S2MM          (static)
 partition i y ─tag─► NMU ┤   stream NoC   ├─► INI ─► NSU ──► x of partition j (inside partition j)
                          └── TDEST picks ─┘
```

- **Endpoints.** Endpoint 2i is partition i and 2i+1 is DMA i, the switch's numbering. Every source
  (each partition's output, each DMA's MM2S) enters the NoC at a static NMU; a 32-bit word travels
  in a 128-bit NoC beat (the stream NoC's narrowest width), tagged with its destination (TDEST).
  DMA inputs are static NSUs; each partition's input is an NSU *inside* the partition, which the PLM
  quiesces while it reconfigures the partition, so the input needs no decoupler.
- **Routing.** The `rps_route` GPIO holds one destination field per source (`w` bits, `w` = bits for
  2N endpoints: field `s` at bits `[w*s, w*s+w)`). Its reset value routes each partition to and from
  its own DMA, so the design works before any routing is written. A chain `dma0 → p0 → p1 → dma0` is
  three writes: field 1 = 0, field 0 = 2, field 2 = 1.
- **Why this shape** (what Vivado 2025.1 allows):
  - A path between two partitions must be owned by a static NoC instance (DRC BD 41-2478), and an INI
    *input* cannot fan out, so a stream cannot pick its destination after leaving a partition.
  - TDEST fan-out needs the destination NSUs in the same or a child block design, so a partition's own
    NMU cannot fan out to static or to another partition. Hence the source NMUs are static and the
    destination NSUs sit in the partitions (UG909's "NMU static, NSU dynamic" topology).
  - The stream NoC carries only 128/256/512-bit TDATA: `rtl/noc_stream.v` widens and narrows.
- **Endpoint budget.** 2N + 1 NMUs (sources plus the DDR port), an NSU in every partition and N NSUs
  outside the partitions (the DMAs'). A pblock takes the NSU sites of its clock regions but not the NMU
  sites, so static NMUs may sit in a partition's row. The VE2302 has five of each in one column, X1
  (`clock_regions` in `boards.py`), so the NoC interconnect takes 1–2 partitions; `pynq-pr validate`
  checks this budget for any board.
- **Route changes** apply from the next packet: each source takes its destination at a packet's first
  beat and keeps it until TLAST.
- **Simulation.** `pynq-pr sim` models the default routes (each partition with its DMA); chaining over
  the NoC is not simulated yet.

## Runtime (plan, not yet run)

1. Boot with the `BOOT.BIN` above: the static design and the first module of every partition are loaded.
2. Attach to it without downloading: `Overlay("<project>.pdi", download=False)` with its `.hwh` (the
   VD100's PYNQ backend, `pynq_backends.versal`, reads Versal HWH files).
3. Load a partial: decouple the partition (`gpio_decouple`, as on the Zynq boards), copy
   `<partition>_<cell>.pdi` to `/lib/firmware`, write `1` to `/sys/class/fpga_manager/fpga0/flags` and the
   file name to `.../firmware` (or `fpgautil -b <file>.pdi -f Partial`), then recouple. The kernel hands the
   image to the PLM (`zynqmp_pm_load_pdi`).

`pynq_pr.overlay` needs two changes for this: no `PL.reset()`/full download for a static design that
booted with the board, and `.pdi` files written to `/lib/firmware` as they are (PYNQ's `.bit` to `.bin`
conversion does not apply). Both wait for the board.

To measure first: the time to load a partial PDI (and a full PL PDI of the same size) through the FPGA
manager, against the KV260's 237 MB/s (fpga_manager) and 524 MB/s (ICAP) in the paper.

## Checked (Vivado 2025.1, no board)

| Example | Partitions | Static / partial PDIs | Worst WNS / WHS | pr_verify | Partials' parent |
|---|---|---|---|---|---|
| `add_sub/pr_vd100.yaml` (switch) | 3 (rows Y2, Y3; X2Y1) | 1.6 MB / 337–515 KB | +3.45 / +0.017 ns | compatible | static PL image ID |
| `vision/pr_vd100.yaml` (switch) | 2 (rows Y2, Y3) | 1.6 MB / 547–586 KB | +4.57 / +0.017 ns | compatible | static PL image ID |
| `vision/pr_vd100_noc.yaml` (NoC) | 2 (rows Y2, Y3) | 1.6 MB / 551–588 KB | +4.30 / +0.017 ns | compatible | static PL image ID |

- DRC: warnings only, none about the floorplan (pblocks are aligned to programmable units, DRC HDPR-147).
- Images: `bootgen -arch versal -read <file>.pdi` shows every partial's `pl_cfi` image naming the static
  image's PL `unique_id` as `parent_unique_id`, the check the PLM makes before loading a partial; both
  modules of a partition share the partition's image ID. NoC-mode partials carry 8 configuration
  partitions, switch-mode partials 4: the partition's NoC endpoint is programmed with it.
- NoC mode: `report_noc_qos` is OPTIMAL with every source-to-destination path; placement uses all five
  NMU512 sites (DDR port, two DMA and two partition sources) and puts each partition's NSU in its row.
- Simulation: `pynq-pr sim -c pr_vd100.yaml --test pr_test.py` passes, as for the Z1.
