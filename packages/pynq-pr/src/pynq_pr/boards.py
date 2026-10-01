BOARDS = {
    "z1": {
        "part": "xc7z020clg400-1",
        "board_part": "",
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
}


def load_board(board_name):
    if board_name not in BOARDS:
        available = list(BOARDS.keys())
        raise ValueError(f"Unknown board '{board_name}'. Available: {available}")
    return BOARDS[board_name]
