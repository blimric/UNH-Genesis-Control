#!/usr/bin/env python3
"""Run this file by path; the containing directory can have any name."""
from pathlib import Path
import importlib.util
import sys


def load_package():
    name = '_genesis_recording'
    root = Path(__file__).resolve().parent
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, root/'__init__.py',
                                                     submodule_search_locations=[str(root)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        spec.loader.exec_module(package)
    return name


if __name__ == '__main__':
    import importlib
    cli = importlib.import_module(load_package()+'.tools.cli')
    raise SystemExit(cli.main())
