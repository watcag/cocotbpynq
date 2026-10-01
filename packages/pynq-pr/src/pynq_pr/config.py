import yaml
from pathlib import Path

VALID_RECONFIG_METHODS = ("pcap", "icap")
PKG_DIR = Path(__file__).parent


def load_config(config_path, root_dir=None):
    with open(config_path) as f:
        config = yaml.safe_load(f)
    root_dir = Path(root_dir) if root_dir else Path.cwd()
    validate(config, root_dir)
    apply_defaults(config, root_dir)
    return config


def validate(config, root_dir):
    required = ["project", "board", "reconfigurable_partitions"]
    for key in required:
        if key not in config:
            raise ValueError(f"Missing required key: {key}")

    method = config.get("reconfiguration_method", "pcap")
    if method not in VALID_RECONFIG_METHODS:
        raise ValueError(f"Invalid reconfiguration_method '{method}'. Valid: {list(VALID_RECONFIG_METHODS)}")

    partitions = config["reconfigurable_partitions"]
    if not 1 <= len(partitions) <= 4:
        raise ValueError(f"Number of partitions must be between 1 and 4, got {len(partitions)}")

    if "sources" not in config or not config["sources"]:
        raise ValueError("Missing required key: sources")

    seen_partitions = set()
    for part in partitions:
        if "partition_name" not in part:
            raise ValueError("Partition missing required key: partition_name")
        pname = part["partition_name"]
        if pname in seen_partitions:
            raise ValueError(f"Duplicate partition_name: {pname}")
        seen_partitions.add(pname)

        if "modules" not in part or not part["modules"]:
            raise ValueError(f"Partition '{pname}' must have at least one module")

        seen_cells = set()
        for rm in part["modules"]:
            for key in ["cell_name", "top"]:
                if key not in rm:
                    raise ValueError(f"Module in partition '{pname}' missing required key: {key}")
            if rm["cell_name"] in seen_cells:
                raise ValueError(f"Duplicate cell_name in partition '{pname}': {rm['cell_name']}")
            seen_cells.add(rm["cell_name"])

    for src in config["sources"]:
        if not (root_dir / src).exists():
            raise FileNotFoundError(f"Source not found: {root_dir / src}")


def apply_defaults(config, root_dir):
    method = config.get("reconfiguration_method", "pcap")
    config["reconfiguration_method"] = method
    config.setdefault("axis_switch", False)
    config.setdefault("_versatile_freq", 100)  # ICAP runs at 2x this frequency
    config.setdefault("_data_freq", 100)

    dummy_path = str(PKG_DIR / "rtl" / "dummy.v")
    if "sources" not in config:
        config["sources"] = []
    if dummy_path not in config["sources"]:
        config["sources"].append(dummy_path)
