from typing import Dict, List, Optional, Any, TYPE_CHECKING
from pathlib import Path
import subprocess
import logging

from .exceptions import PRBuildError

if TYPE_CHECKING:
    from .system import PRSystem
    from .partition import Partition

logger = logging.getLogger(__name__)


class ReconfigurableModule:
    """Represents a reconfigurable module (RM) that can be loaded into a partition."""

    def __init__(
        self,
        name: str,
        partition_name: str,
        design: str = None,
        sources: List[str] = None,
        parameters: Dict[str, Any] = None,
        port_mapping: Dict[str, str] = None,
        port_compatibility: Dict[str, Dict] = None,
        clocks: List[str] = None,
        resets: List[Any] = None,
        tieoffs: Dict[str, Any] = None,
        interfaces: Dict[str, Dict] = None,
        system: 'PRSystem' = None,
        auto_wrap: bool = False,
        auto_wrap_config: Dict[str, Any] = None,
        ports_override: Dict[str, Dict] = None
    ):
        self.name = name
        self.partition_name = partition_name
        self.system = system

        self.design = design
        self.sources = sources or []
        self.parameters = parameters or {}
        self.clocks = clocks or ['clk']
        self.resets = resets or []
        self.tieoffs = tieoffs or {}
        self.interfaces = interfaces or {}

        self.port_mapping = port_mapping or {}
        self.port_compatibility = port_compatibility or {}

        self.auto_wrap = auto_wrap
        self.auto_wrap_config = auto_wrap_config or {}
        self.ports_override = ports_override

        self._process: Optional[subprocess.Popen] = None
        self._binary_path: Optional[str] = None
        self._built = False

    @property
    def partition(self) -> Optional['Partition']:
        if self.system:
            return self.system.partitions.get(self.partition_name)
        return None

    def build(self, fast: bool = False) -> 'ReconfigurableModule':
        self._built = True
        return self

    def terminate(self, timeout: float = 10.0):
        self._process = None

    @property
    def is_running(self) -> bool:
        if self.system and hasattr(self.system, '_sim_process') and self.system._sim_process:
            partition = self.partition
            if partition and partition.active_rm is self:
                return self.system._sim_process.is_running
        if self._process is not None:
            return self._process.poll() is None
        return False

    @property
    def is_built(self) -> bool:
        return self._built

    def __repr__(self) -> str:
        status = "running" if self.is_running else ("built" if self.is_built else "not built")
        return f"<ReconfigurableModule '{self.name}' partition='{self.partition_name}' status={status}>"
