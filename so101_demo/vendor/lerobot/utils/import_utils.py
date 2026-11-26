"""Minimal imports needed by the vendored, unmodified LeRobot motor bus."""
import importlib.util

_serial_available = importlib.util.find_spec('serial') is not None
_deepdiff_available = importlib.util.find_spec('deepdiff') is not None
_feetech_sdk_available = importlib.util.find_spec('scservo_sdk') is not None

def require_package(package, extra=None, import_name=None):
    if importlib.util.find_spec(import_name or package) is None:
        raise ImportError('Missing package: ' + package)
