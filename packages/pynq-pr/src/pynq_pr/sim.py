"""
Generate a cocotbpynq simulation config from a pynq-pr YAML config.

Generates pr_sim.yaml in sim/<project>/, then invokes run.py.
"""
import shutil
from pathlib import Path

import yaml

from .config import load_config


# Fixed RM boundary ports. All pynq-pr modules share this interface.
BOUNDARY_PORTS = [
    {'name': 'rst_n',                       'direction': 'to_rm',   'width': 1},
    # AXI-Stream in
    {'name': 'x_TDATA',                     'direction': 'to_rm',   'width': 32},
    {'name': 'x_TVALID',                    'direction': 'to_rm',   'width': 1},
    {'name': 'x_TREADY',                    'direction': 'from_rm', 'width': 1},
    {'name': 'x_TLAST',                     'direction': 'to_rm',   'width': 1},
    # AXI-Stream out
    {'name': 'y_TDATA',                     'direction': 'from_rm', 'width': 32},
    {'name': 'y_TVALID',                    'direction': 'from_rm', 'width': 1},
    {'name': 'y_TREADY',                    'direction': 'to_rm',   'width': 1},
    {'name': 'y_TLAST',                     'direction': 'from_rm', 'width': 1},
    # AXI-Lite slave (inputs to RM)
    {'name': 's_axi_AXILiteS_AWVALID',      'direction': 'to_rm',   'width': 1},
    {'name': 's_axi_AXILiteS_AWADDR',       'direction': 'to_rm',   'width': 8},
    {'name': 's_axi_AXILiteS_WVALID',       'direction': 'to_rm',   'width': 1},
    {'name': 's_axi_AXILiteS_WDATA',        'direction': 'to_rm',   'width': 32},
    {'name': 's_axi_AXILiteS_WSTRB',        'direction': 'to_rm',   'width': 4},
    {'name': 's_axi_AXILiteS_ARVALID',      'direction': 'to_rm',   'width': 1},
    {'name': 's_axi_AXILiteS_ARADDR',       'direction': 'to_rm',   'width': 8},
    {'name': 's_axi_AXILiteS_RREADY',       'direction': 'to_rm',   'width': 1},
    {'name': 's_axi_AXILiteS_BREADY',       'direction': 'to_rm',   'width': 1},
    # AXI-Lite slave (outputs from RM)
    {'name': 's_axi_AXILiteS_AWREADY',      'direction': 'from_rm', 'width': 1},
    {'name': 's_axi_AXILiteS_WREADY',       'direction': 'from_rm', 'width': 1},
    {'name': 's_axi_AXILiteS_ARREADY',      'direction': 'from_rm', 'width': 1},
    {'name': 's_axi_AXILiteS_RVALID',       'direction': 'from_rm', 'width': 1},
    {'name': 's_axi_AXILiteS_RDATA',        'direction': 'from_rm', 'width': 32},
    {'name': 's_axi_AXILiteS_RRESP',        'direction': 'from_rm', 'width': 2},
    {'name': 's_axi_AXILiteS_BVALID',       'direction': 'from_rm', 'width': 1},
    {'name': 's_axi_AXILiteS_BRESP',        'direction': 'from_rm', 'width': 2},
]

DMA_BASE_ADDR = 0x40400000
DMA_ADDR_RANGE = 0x10000
SWITCH_BASE_ADDR = 0x44A00000
SWITCH_ADDR_RANGE = 0x10000
RP_CTRL_BASE_ADDR = 0x43C00000
RP_CTRL_ADDR_RANGE = 0x10000


def _resolve_param_value(value, root_dir):
    """Resolve file-like string parameters to absolute paths for simulation."""
    if not isinstance(value, str):
        return value

    raw_path = Path(value).expanduser()
    candidates = [raw_path] if raw_path.is_absolute() else [(root_dir / raw_path)]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())

    return value


def _split_sim_sources_and_includes(sources_abs):
    """Treat Verilog headers as include files instead of standalone sources."""
    sim_sources = []
    include_dirs = []

    for source in sources_abs:
        source_path = Path(source)
        include_dir = str(source_path.parent)
        if include_dir not in include_dirs:
            include_dirs.append(include_dir)

        if source_path.suffix.lower() in {'.vh', '.svh'}:
            continue

        sim_sources.append(source)

    return sim_sources, include_dirs


def _build_cocotbpynq_yaml(config, sim_sources_abs, include_dirs, root_dir):
    """Build the cocotbpynq YAML dict from a pynq-pr config."""
    partitions = config['reconfigurable_partitions']

    # Static region interfaces (one DMA per partition)
    interfaces = {}
    if config.get('axis_switch'):
        interfaces['switch_ctrl'] = {
            'type': 'axil',
            'direction': 'subordinate',
            'dw': 32,
            'base_addr': SWITCH_BASE_ADDR,
            'addr_range': SWITCH_ADDR_RANGE,
        }
    for i, part in enumerate(partitions):
        pname = part['partition_name']
        dma = f'{pname}/dma'
        interfaces[f'{pname}_ctrl'] = {
            'type': 'axil',
            'direction': 'subordinate',
            'dw': 32,
            'partition': pname,
            'port_prefix': f'{pname}_ctrl',
            'base_addr': RP_CTRL_BASE_ADDR + i * RP_CTRL_ADDR_RANGE,
            'addr_range': RP_CTRL_ADDR_RANGE,
        }
        interfaces[f'x_{pname}'] = {
            'type': 'sb',
            'direction': 'subordinate',
            'dw': 32,
            'dma_instance': dma,
            'base_addr': DMA_BASE_ADDR + i * DMA_ADDR_RANGE,
            'addr_range': DMA_ADDR_RANGE,
        }
        interfaces[f'y_{pname}'] = {
            'type': 'sb',
            'direction': 'manager',
            'dw': 32,
            'dma_instance': dma,
        }

    # Partition definitions
    part_defs = []
    for part in partitions:
        pname = part['partition_name']
        first_rm = part['modules'][0]
        initial_rm = f"{pname}_{first_rm['cell_name']}"
        part_defs.append({
            'name': pname,
            'rm_module': first_rm['top'],
            'clock': 'clk',
            'boundary': BOUNDARY_PORTS,
            'initial_rm': initial_rm,
        })

    # Reconfigurable module definitions
    rm_defs = []
    for part in partitions:
        pname = part['partition_name']
        for rm in part['modules']:
            rm_name = f"{pname}_{rm['cell_name']}"
            rm_def = {
                'name': rm_name,
                'partition': pname,
                'design': rm['top'],
                'sources': [str(s) for s in sim_sources_abs],
                'include_dirs': include_dirs,
                'auto_wrap': True,
                'auto_wrap_config': {'clock_name': 'clk'},
            }
            if rm.get('parameters'):
                rm_def['parameters'] = {
                    key: _resolve_param_value(value, root_dir)
                    for key, value in rm['parameters'].items()
                }
            rm_defs.append(rm_def)

    return {
        'version': '1.0',
        'simulation': {
            'tool': 'verilator',
            'build_dir': 'build',
        },
        'static_region': {
            'name': 'sim_static',
            'design': 'sim_static',
            'auto_wrap': True,
            'auto_wrap_config': {
                'clock_name': 'clk',
                'reset_name': 'rst_n',
                'reset_active_low': True,
            },
            'interfaces': interfaces,
        },
        'partitions': part_defs,
        'reconfigurable_modules': rm_defs,
    }


def generate_sim_config(config_path, force=False):
    """Generate cocotbpynq pr_sim.yaml from a pynq-pr config.

    Args:
        config_path: path to pynq-pr YAML config
        force: remove existing sim directory before generating

    Returns:
        Path to the generated pr_sim.yaml
    """
    root_dir = Path.cwd()
    config = load_config(config_path)
    project = config['project']

    sim_dir = root_dir / 'sim' / project
    if sim_dir.exists():
        if force:
            shutil.rmtree(sim_dir)
            print(f"Removed existing sim directory: {sim_dir}")
        else:
            raise FileExistsError(
                f"Sim directory already exists: {sim_dir}\n"
                "Use -f/--force to overwrite."
            )

    sim_dir.mkdir(parents=True, exist_ok=True)

    # Resolve source paths to absolute
    sources_abs = []
    for src in config['sources']:
        src_path = Path(src)
        resolved = src_path.resolve() if src_path.is_absolute() else (root_dir / src).resolve()
        sources_abs.append(resolved)

    sim_sources_abs, include_dirs = _split_sim_sources_and_includes(sources_abs)

    # Generate pr_sim.yaml
    sim_yaml = _build_cocotbpynq_yaml(config, sim_sources_abs, include_dirs, root_dir)
    yaml_path = sim_dir / 'pr_sim.yaml'
    with open(yaml_path, 'w') as f:
        yaml.dump(sim_yaml, f, default_flow_style=False, sort_keys=False)
    print(f"Generated {yaml_path}")

    return yaml_path
