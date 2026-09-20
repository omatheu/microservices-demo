#!/usr/bin/env python3

import pathlib
import sys


CONTROLLER_DIR = pathlib.Path(__file__).resolve().parents[1] / "pdt" / "controller"
sys.path.insert(0, str(CONTROLLER_DIR))

from checkout_pdt_controller import main, safety_violations  # noqa: E402,F401


if __name__ == "__main__":
    sys.argv.insert(1, "decide")
    main()
