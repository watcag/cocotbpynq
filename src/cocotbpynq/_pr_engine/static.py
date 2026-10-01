from typing import Dict, List, Optional, Any, TYPE_CHECKING
from pathlib import Path
import subprocess
import logging

from .exceptions import PRBuildError

if TYPE_CHECKING:
    from .system import PRSystem

logger = logging.getLogger(__name__)


class StaticRegion:
    """Represents the static (non-reconfigurable) region of an FPGA."""

    def __init__(
        self,
        name: str = 'static_region',
        design: Any = None,
        sources: List[str] = None,
        parameters: Dict[str, Any] = None,
        interfaces: Dict[str, Dict] = None,
        clocks: List[str] = None,
        resets: List[Any] = None,
        system: 'PRSystem' = None,
        build_dir: str = None,
        auto_wrap: bool = False,
        auto_wrap_config: Dict[str, Any] = None,
        ports_override: Dict[str, Dict] = None
    ):
        self.name = name
        self.design = design
        self.sources = sources or []
        self.parameters = parameters or {}
        self.interfaces = interfaces or {}
        self.clocks = clocks or ['clk']
        self.resets = resets or []
        self.system = system
        self.build_dir = build_dir or 'build/pr/static'
        self.auto_wrap = auto_wrap
        self.auto_wrap_config = auto_wrap_config or {}
        self.ports_override = ports_override
        self._process: Optional[subprocess.Popen] = None
        self._built = False
        self._running = False
        self._module_info = None

    def build(self, fast: bool = False) -> 'StaticRegion':
        self._built = True
        logger.info(f"Static region '{self.name}' artifacts ready")
        return self

    @property
    def is_running(self) -> bool:
        if self.system and hasattr(self.system, '_sim_process') and self.system._sim_process:
            return self.system._sim_process.is_running
        return self._running

    @property
    def is_built(self) -> bool:
        return self._built

    def __repr__(self) -> str:
        status = "running" if self._running else ("built" if self._built else "not built")
        return f"<StaticRegion '{self.name}' status={status}>"
