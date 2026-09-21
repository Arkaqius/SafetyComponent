import sys
from pathlib import Path

# Ensure test helper modules (including stub packages) are importable
TESTS_DIR = Path(__file__).parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import pytest  # noqa: E402
from .fixtures.hass_fixture import *  # noqa: F401,F403
from .fixtures.test_sf_cfgs import *  # noqa: F401,F403
