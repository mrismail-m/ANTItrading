#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
ANTItrading - Root Entrypoint
===============================================================================
- When invoked by Appwrite Functions: delegates to deploy.appwrite_function.main(context).
- When executed from CLI (python3 main.py): runs the trading pass.
===============================================================================
"""

import sys
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def main(context=None):
    """Appwrite Functions entrypoint."""
    if context is not None:
        from deploy.appwrite_function import main as appwrite_handler
        return appwrite_handler(context)

    # CLI fallback execution
    from scripts.run_trader import run_trader_pass
    return run_trader_pass()


if __name__ == "__main__":
    from scripts.run_trader import run_trader_pass
    run_trader_pass()
