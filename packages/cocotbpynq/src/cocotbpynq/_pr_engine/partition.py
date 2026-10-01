from typing import Dict, List, Optional, Any, TYPE_CHECKING
import logging

from .exceptions import PRReconfigurationError

if TYPE_CHECKING:
    from .system import PRSystem
    from .module import ReconfigurableModule

logger = logging.getLogger(__name__)


class Partition:
    """Logical container for a reconfigurable partition."""

    def __init__(
        self,
        name: str,
        interface: Dict[str, Dict[str, Any]],
        system: 'PRSystem' = None,
        initial_rm: str = None,
    ):
        self.name = name
        self.interface = interface
        self.system = system
        self.initial_rm_name = initial_rm

        self.registered_rms: Dict[str, 'ReconfigurableModule'] = {}
        self.active_rm: Optional['ReconfigurableModule'] = None
        self._intfs: Dict[str, Any] = {}

    def register_rm(self, rm: 'ReconfigurableModule'):
        if rm.partition_name != self.name:
            raise PRReconfigurationError(
                f"Cannot register RM '{rm.name}' with partition '{self.name}': "
                f"RM belongs to partition '{rm.partition_name}'"
            )
        self.registered_rms[rm.name] = rm

    def load_rm(self, rm: 'ReconfigurableModule') -> bool:
        if rm.partition_name != self.name:
            raise PRReconfigurationError(
                f"RM '{rm.name}' belongs to partition '{rm.partition_name}', "
                f"cannot load into partition '{self.name}'"
            )
        if self.active_rm is not None:
            self.unload_rm()
        self.active_rm = rm
        return True

    def unload_rm(self) -> bool:
        if self.active_rm is None:
            return True
        self.active_rm.terminate()
        self.active_rm = None
        return True

    @property
    def is_loaded(self) -> bool:
        return self.active_rm is not None

    @property
    def is_running(self) -> bool:
        if self.active_rm is None:
            return False
        return self.active_rm.is_running

    def get_rm_names(self) -> List[str]:
        return list(self.registered_rms.keys())

    def get_rm(self, name: str) -> Optional['ReconfigurableModule']:
        return self.registered_rms.get(name)

    def terminate(self, timeout: float = 10.0):
        self.unload_rm()

    def __repr__(self) -> str:
        active = self.active_rm.name if self.active_rm else "none"
        return f"<Partition '{self.name}' active_rm='{active}' registered={len(self.registered_rms)}>"
