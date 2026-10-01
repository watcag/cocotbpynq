from typing import Dict, List, Optional, Union, Any
from pathlib import Path
import json

from .exceptions import PRConfigError

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class PRConfig:
    """Loader and validator for PR configuration files."""

    SUPPORTED_VERSIONS = ['1.0']
    REQUIRED_FIELDS = ['partitions', 'reconfigurable_modules']

    def __init__(self):
        self.version: str = '1.0'
        self.simulation: Dict[str, Any] = {}
        self.static_region: Optional[Dict[str, Any]] = None
        self.partitions: List[Dict[str, Any]] = []
        self.reconfigurable_modules: List[Dict[str, Any]] = []
        self._source_path: Optional[Path] = None

    @classmethod
    def load(cls, path: Union[str, Path]) -> 'PRConfig':
        path = Path(path)
        if not path.exists():
            raise PRConfigError(f"Configuration file not found: {path}")

        suffix = path.suffix.lower()
        with open(path, 'r') as f:
            if suffix in ['.yaml', '.yml']:
                if not HAS_YAML:
                    raise PRConfigError("PyYAML not installed. Install with: pip install pyyaml")
                data = yaml.safe_load(f)
            elif suffix == '.json':
                data = json.load(f)
            else:
                raise PRConfigError(f"Unsupported config format: {suffix}. Use .yaml, .yml, or .json")

        config = cls.from_dict(data)
        config._source_path = path
        return config

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PRConfig':
        config = cls()
        config._validate_and_load(data)
        return config

    def _validate_and_load(self, data: Dict[str, Any]):
        if not isinstance(data, dict):
            raise PRConfigError("Configuration must be a dictionary")

        self.version = str(data.get('version', '1.0'))
        if self.version not in self.SUPPORTED_VERSIONS:
            raise PRConfigError(f"Unsupported config version: {self.version}")

        for field in self.REQUIRED_FIELDS:
            if field not in data:
                raise PRConfigError(f"Missing required field: '{field}'")

        self.simulation = data.get('simulation', {})
        self.static_region = data.get('static_region')
        self.partitions = data.get('partitions', [])
        self.reconfigurable_modules = data.get('reconfigurable_modules', [])

        self._apply_defaults()
        self._validate_partitions()
        self._validate_rms()

    def _apply_defaults(self):
        DEFAULT_CLOCKS = ['clk']
        DEFAULT_RESETS = [{'name': 'rst_n', 'polarity': 'negative'}]

        if self.static_region:
            if 'design' not in self.static_region:
                self.static_region['design'] = self.static_region.get('name', 'static_region')
            if 'clocks' not in self.static_region:
                awc = self.static_region.get('auto_wrap_config', {})
                if 'clock_name' in awc:
                    self.static_region['clocks'] = [awc['clock_name']]
                else:
                    self.static_region['clocks'] = DEFAULT_CLOCKS
            if 'resets' not in self.static_region:
                self.static_region['resets'] = DEFAULT_RESETS

        for part in self.partitions:
            if 'clocks' not in part:
                if 'clock' in part:
                    part['clocks'] = [part['clock']]
                else:
                    part['clocks'] = ['clk']

        partition_interfaces = {}
        for part in self.partitions:
            partition_interfaces[part['name']] = part.get('interface', {})

        for rm in self.reconfigurable_modules:
            if 'design' not in rm:
                rm['design'] = rm['name']
            if 'clocks' not in rm:
                rm['clocks'] = DEFAULT_CLOCKS
            if 'resets' not in rm:
                rm['resets'] = DEFAULT_RESETS
            if 'port_mapping' not in rm:
                partition_name = rm.get('partition')
                if partition_name and partition_name in partition_interfaces:
                    part_intf = partition_interfaces[partition_name]
                    rm['port_mapping'] = {port: port for port in part_intf}

    def _validate_partitions(self):
        partition_names = set()
        for i, part in enumerate(self.partitions):
            if not isinstance(part, dict):
                raise PRConfigError(f"Partition {i} must be a dictionary")
            if 'name' not in part:
                raise PRConfigError(f"Partition {i} missing 'name' field")
            name = part['name']
            if name in partition_names:
                raise PRConfigError(f"Duplicate partition name: '{name}'")
            partition_names.add(name)
            if 'interface' not in part and 'boundary' not in part:
                raise PRConfigError(f"Partition '{name}' must have 'interface' or 'boundary' field")
            if 'boundary' in part:
                self._validate_boundary(part['boundary'], f"partition '{name}'")

    def _validate_boundary(self, boundary: list, context: str):
        if not isinstance(boundary, list):
            raise PRConfigError(f"Boundary for {context} must be a list")
        valid_directions = ['to_rm', 'from_rm']
        port_names = set()
        for i, port in enumerate(boundary):
            if not isinstance(port, dict):
                raise PRConfigError(f"Boundary port {i} in {context} must be a dictionary")
            if 'name' not in port:
                raise PRConfigError(f"Boundary port {i} in {context} missing 'name'")
            name = port['name']
            if name in port_names:
                raise PRConfigError(f"Duplicate boundary port name '{name}' in {context}")
            port_names.add(name)
            if 'direction' not in port:
                raise PRConfigError(f"Boundary port '{name}' in {context} missing 'direction'")
            if port['direction'] not in valid_directions:
                raise PRConfigError(
                    f"Invalid direction '{port['direction']}' for boundary port "
                    f"'{name}' in {context}. Valid: {valid_directions}"
                )

    def _validate_rms(self):
        rm_names = set()
        partition_names = {p['name'] for p in self.partitions}
        for i, rm in enumerate(self.reconfigurable_modules):
            if not isinstance(rm, dict):
                raise PRConfigError(f"RM {i} must be a dictionary")
            if 'name' not in rm:
                raise PRConfigError(f"RM {i} missing 'name' field")
            name = rm['name']
            if name in rm_names:
                raise PRConfigError(f"Duplicate RM name: '{name}'")
            rm_names.add(name)
            if 'partition' not in rm:
                raise PRConfigError(f"RM '{name}' missing 'partition' field")
            if rm['partition'] not in partition_names:
                raise PRConfigError(f"RM '{name}' references unknown partition: '{rm['partition']}'")
            if 'design' not in rm and 'sources' not in rm:
                raise PRConfigError(f"RM '{name}' must have 'design' or 'sources' field")

    def get_partition(self, name: str) -> Optional[Dict[str, Any]]:
        for part in self.partitions:
            if part['name'] == name:
                return part
        return None

    def get_rm(self, name: str) -> Optional[Dict[str, Any]]:
        for rm in self.reconfigurable_modules:
            if rm['name'] == name:
                return rm
        return None

    def get_rms_for_partition(self, partition_name: str) -> List[Dict[str, Any]]:
        return [rm for rm in self.reconfigurable_modules if rm['partition'] == partition_name]

    def get_initial_rm(self, partition_name: str) -> Optional[str]:
        part = self.get_partition(partition_name)
        if part:
            return part.get('initial_rm')
        return None
