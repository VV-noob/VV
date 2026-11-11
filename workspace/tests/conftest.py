"""Shared pytest fixtures/path setup for REQ-MOTOR-001 tests.

Ensures the repository root (which holds ``motor_controller.py``) is importable
regardless of the directory pytest is invoked from.

[Trace: REQ-MOTOR-001]
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
