"""Root conftest.py - sets up Python path before any test imports."""
import sys
import os

# Add project root to path at the earliest possible moment
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Pre-import services.ton_service to ensure it's available for all test modules
# This is needed because the services/ directory at project root can conflict
# with tests/services/ namespace during pytest collection
from services.ton_service import TonService
