#!/usr/bin/env python
"""Compatibility wrapper for the Tushare data service.

Prefer:
    python -m app.data_service ...
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data_service.runner import main

if __name__ == "__main__":
    main()
