"""Test setup: config.py is gitignored, so supply a stub when it is missing."""
import sys
import types

try:
    import config  # noqa: F401
except ImportError:
    stub = types.ModuleType("config")
    stub.RED = stub.GREEN = stub.YELLOW = 0
    stub.LOG_CHAN = 0
    sys.modules["config"] = stub
