"""
Partial reconfiguration support for cocotbpynq.

Provides:
- PRSystem: configures and builds the swap-aware PR simulation.
- PRCocotbRunner: orchestrates building and running a cocotb PR simulation.

Internal (used by Overlay.pr_download):
- CtrlMailbox, pr_reconfigure: cross-process reconfiguration via SHM.
"""

from cocotbpynq._pr_engine import PRSystem
from .cocotb_runner import PRCocotbRunner

__all__ = ['PRSystem', 'PRCocotbRunner']
