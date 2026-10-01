import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import pyslang
import pyslang.ast
import pyslang.syntax

logger = logging.getLogger(__name__)


class PortType(Enum):
    CLOCK = auto()
    RESET = auto()
    DATA = auto()


class ResetPolarity(Enum):
    ACTIVE_HIGH = auto()
    ACTIVE_LOW = auto()
    UNKNOWN = auto()


@dataclass
class PortInfo:
    name: str
    direction: str  # 'input', 'output', 'inout'
    width: int
    port_type: PortType = PortType.DATA
    is_signed: bool = False
    is_array: bool = False
    array_dims: Tuple[int, ...] = ()

    @property
    def total_bits(self) -> int:
        total = self.width
        for dim in self.array_dims:
            total *= dim
        return total


@dataclass
class ParameterInfo:
    name: str
    value: Any
    width: int = 32
    is_localparam: bool = False


@dataclass
class ModuleInfo:
    name: str
    ports: Dict[str, PortInfo] = field(default_factory=dict)
    parameters: Dict[str, ParameterInfo] = field(default_factory=dict)
    source_file: Optional[str] = None

    def input_ports(self) -> List[PortInfo]:
        return [p for p in self.ports.values() if p.direction == 'input']

    def output_ports(self) -> List[PortInfo]:
        return [p for p in self.ports.values() if p.direction == 'output']

    def data_ports(self) -> List[PortInfo]:
        return [p for p in self.ports.values() if p.port_type == PortType.DATA]

    def clock_ports(self) -> List[PortInfo]:
        return [p for p in self.ports.values() if p.port_type == PortType.CLOCK]

    def reset_ports(self) -> List[PortInfo]:
        return [p for p in self.ports.values() if p.port_type == PortType.RESET]


class RTLParser:
    """Parse RTL files to extract module port definitions using pyslang."""

    CLOCK_NAMES = {'clk', 'clock', 'ck', 'pclk', 'hclk', 'fclk', 'aclk', 'sysclk', 'refclk'}
    RESET_NAMES = {
        'rst_n': ResetPolarity.ACTIVE_LOW,
        'rstn': ResetPolarity.ACTIVE_LOW,
        'reset_n': ResetPolarity.ACTIVE_LOW,
        'resetn': ResetPolarity.ACTIVE_LOW,
        'arst_n': ResetPolarity.ACTIVE_LOW,
        'rst': ResetPolarity.ACTIVE_HIGH,
        'reset': ResetPolarity.ACTIVE_HIGH,
        'arst': ResetPolarity.ACTIVE_HIGH,
    }

    def __init__(self, classification=None, strict_matching: bool = False):
        self.strict_matching = strict_matching

    def parse_module(
        self,
        sources: List[str],
        module_name: str = None,
        include_dirs: List[str] = None,
        defines: Dict[str, str] = None
    ) -> ModuleInfo:
        source_paths = [str(Path(s).resolve()) for s in sources]

        trees = []
        for path in source_paths:
            tree = pyslang.syntax.SyntaxTree.fromFile(path)
            if tree is None:
                raise ValueError(f"Failed to parse file: {path}")
            trees.append(tree)

        compilation = pyslang.ast.Compilation()
        for tree in trees:
            compilation.addSyntaxTree(tree)
        compilation.getAllDiagnostics()

        root = compilation.getRoot()
        top_instances = list(root.topInstances)

        if not top_instances:
            raise ValueError(f"No top-level modules found in sources: {sources}")

        target_instance = None
        if module_name:
            for inst in top_instances:
                if inst.name == module_name:
                    target_instance = inst
                    break
            if target_instance is None:
                available = [inst.name for inst in top_instances]
                raise ValueError(f"Module '{module_name}' not found. Available: {available}")
        else:
            target_instance = top_instances[0]
            module_name = target_instance.name

        ports = self._extract_ports(target_instance)

        return ModuleInfo(
            name=module_name,
            ports=ports,
            source_file=source_paths[0] if source_paths else None
        )

    def _extract_ports(self, instance) -> Dict[str, PortInfo]:
        ports = {}
        for port in instance.body.portList:
            port_info = self._parse_port(port)
            if port_info:
                ports[port_info.name] = port_info
        return ports

    def _parse_port(self, port) -> Optional[PortInfo]:
        try:
            name = port.name
            direction_map = {
                pyslang.ast.ArgumentDirection.In: 'input',
                pyslang.ast.ArgumentDirection.Out: 'output',
                pyslang.ast.ArgumentDirection.InOut: 'inout',
            }
            direction = direction_map.get(port.direction)
            if direction is None:
                return None

            width = 1
            is_signed = False
            if hasattr(port, 'type'):
                if hasattr(port.type, 'bitWidth'):
                    width = port.type.bitWidth
                if hasattr(port.type, 'isSigned'):
                    is_signed = port.type.isSigned

            port_type = self._classify_port(name, direction, width)

            return PortInfo(
                name=name,
                direction=direction,
                width=width,
                port_type=port_type,
                is_signed=is_signed,
            )
        except Exception as e:
            logger.warning(f"Failed to parse port {port}: {e}")
            return None

    def _classify_port(self, name: str, direction: str, width: int) -> PortType:
        if self.strict_matching:
            return PortType.DATA
        low = name.lower()
        if direction == 'input' and width == 1:
            if low in self.CLOCK_NAMES or low.startswith('clk_') or low.endswith('_clk'):
                return PortType.CLOCK
            if low in self.RESET_NAMES or low.endswith('_rst_n') or low.endswith('_rst'):
                return PortType.RESET
        return PortType.DATA
