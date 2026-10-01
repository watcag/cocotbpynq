"""
Partial reconfiguration support for cocotbpynq.

Provides:
- PRCocotbRunner: orchestrates building and running a cocotb PR simulation.

Internal (used by Overlay.pr_download):
- CtrlMailbox, pr_reconfigure: cross-process reconfiguration via SHM.
"""

from .cocotb_runner import PRCocotbRunner

__all__ = ['PRCocotbRunner']
