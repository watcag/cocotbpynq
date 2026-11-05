BOARDS = {
    "z1": {
        "part": "xc7z020clg400-1",
        "board_part": "",
        "family": "zynq",
        "vivado": "2022.2",
        "icap_primitive": "ICAPE2",  # Zynq-7000
        "frame_height": 50,
        "clock_regions": {
            "X0Y0": {"SLICE": (0,  49,  0,  49)},
            "X0Y1": {"SLICE": (26, 49,  50, 99)},
            "X0Y2": {"SLICE": (26, 49,  100, 149)},
            "X1Y0": {"SLICE": (50, 113, 0,  49)},
            "X1Y1": {"SLICE": (50, 113, 50, 99)},
            "X1Y2": {"SLICE": (50, 113, 100, 149)},
        },
        "reconfigurable_regions": ["X0Y0", "X1Y1", "X1Y2", "X0Y2", "X0Y1"],
        "reconfigurable_regions_lte2": ["X0Y0", "X1Y0", "X1Y1", "X1Y2"],
        "pblock_resources": ["SLICE", "DSP", "RAMB"],
    },
    "kv260": {
        "part": "xck26-sfvc784-2LV-c",
        "board_part": "xilinx.com:kv260_som:part0:1.3",
        "family": "zynq",
        "vivado": "2022.2",
        "icap_primitive": "ICAPE3",  # Zynq UltraScale+
        "frame_height": 60,
        "clock_regions": {
            "X0Y0": {"SLICE": (0,  22, 0,   59)},
            "X0Y1": {"SLICE": (0,  22, 60,  119)},
            "X0Y2": {"SLICE": (0,  22, 120, 179)},
            "X0Y3": {"SLICE": (0,  22, 180, 239)},
            "X1Y0": {"SLICE": (23, 40, 0,   59)},
            "X1Y1": {"SLICE": (23, 40, 60,  119)},
            "X1Y2": {"SLICE": (23, 40, 120, 179)},
            "X1Y3": {"SLICE": (23, 40, 180, 239)},
            "X2Y0": {"SLICE": (41, 60, 0,   59)},
            "X2Y1": {"SLICE": (41, 60, 60,  119)},
            "X2Y2": {"SLICE": (41, 60, 120, 179)},
            "X2Y3": {"SLICE": (41, 60, 180, 239)},
        },
        "reconfigurable_regions": [
            # Leave only X0Y0 and X1Y0 static; all other clock regions are
            # available for dynamic partitions.
            "X0Y1", "X0Y2", "X0Y3",
            "X1Y1", "X1Y2", "X1Y3",
            "X2Y0", "X2Y1", "X2Y2", "X2Y3",
        ],
        "pblock_resources": ["SLICE", "DSP", "RAMB", "URAM"],
    },
    "vd100": {
        "part": "xcve2302-sfva784-1LP-e-s",
        "board_part": "",  # Alinx ships no board files: ps_vd100.tcl and constraints/vd100.xdc
        "family": "versal",
        "vivado": "2025.1",
        "icap_primitive": None,  # Versal has no ICAP: the PMC loads every partial PDI
        # Fabric clock regions: LUTs, DSP58s and PL NoC endpoints (NMU512/NSU512 pairs). DSPs are
        # only in column X2, NoC endpoints only in column X1 (one VNoC column), and row Y3 is half
        # height. X0Y1 holds the PS side of the NoC and no fabric.
        "clock_regions": {
            "X0Y2": {"LUT": 21504, "DSP": 0,   "NOC": 0},
            "X0Y3": {"LUT": 9856,  "DSP": 0,   "NOC": 0},
            "X1Y1": {"LUT": 14720, "DSP": 0,   "NOC": 2},
            "X1Y2": {"LUT": 30720, "DSP": 0,   "NOC": 2},
            "X1Y3": {"LUT": 14080, "DSP": 0,   "NOC": 1},
            "X2Y1": {"LUT": 23552, "DSP": 184, "NOC": 0},
            "X2Y2": {"LUT": 24576, "DSP": 192, "NOC": 0},
            "X2Y3": {"LUT": 11264, "DSP": 88,  "NOC": 0},
        },
        # Partitions per partition count, as whole rows so each one gets every resource type and,
        # for one or two partitions, its own NoC endpoints. X1Y1 always stays static, with the
        # static design's NoC endpoints (ps_vd100.tcl pins the DDR port there).
        "layouts": {
            1: [["X0Y2", "X1Y2", "X2Y2", "X0Y3", "X1Y3", "X2Y3"]],
            2: [["X0Y2", "X1Y2", "X2Y2"], ["X0Y3", "X1Y3", "X2Y3"]],
            3: [["X0Y2", "X1Y2", "X2Y2"], ["X0Y3", "X1Y3", "X2Y3"], ["X2Y1"]],
        },
        # IRI_QUAD and BLI sites belong to the same programmable units as the fabric sites; without
        # them a pblock is not aligned to programmable units (DRC HDPR-147).
        "pblock_resources": ["SLICE", "DSP", "RAMB", "URAM", "IRI_QUAD", "BLI"],
    },
}


def load_board(board_name):
    if board_name not in BOARDS:
        available = list(BOARDS.keys())
        raise ValueError(f"Unknown board '{board_name}'. Available: {available}")
    return BOARDS[board_name]
