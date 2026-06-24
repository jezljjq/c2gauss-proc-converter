# -*- coding: utf-8 -*-
"""Old-style command entry for V32.

Usage example:
  python c2gauss_v32.py --c-file examples/input/amwkpl06_sample.c --loader-cfg examples/input/loader.cfg --middle-table EVMID_AMWKSTU1 --out-dir output
"""
from __future__ import print_function

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from c2gauss_v32.cli import main


if __name__ == '__main__':
    sys.exit(main())
