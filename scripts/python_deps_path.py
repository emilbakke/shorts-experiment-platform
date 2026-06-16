#!/usr/bin/env python3
from pathlib import Path
import sys
print(Path(__file__).resolve().parents[1] / f".python_deps_{sys.version_info.major}{sys.version_info.minor}")
