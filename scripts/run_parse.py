#!/usr/bin/env python3
"""Run the offline parser pipeline. Equivalent to: cuk-parse"""

import subprocess
import sys

sys.exit(subprocess.call(["cuk-parse", *sys.argv[1:]]))
