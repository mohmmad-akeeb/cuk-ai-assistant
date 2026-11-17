#!/usr/bin/env python3
"""Run the full site crawl.  Equivalent to: cuk-crawl crawl"""

import subprocess
import sys

sys.exit(subprocess.call(["cuk-crawl", "crawl", *sys.argv[1:]]))
