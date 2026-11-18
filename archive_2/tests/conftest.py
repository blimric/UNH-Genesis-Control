import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_launcher',ROOT/'run.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
PACKAGE=launcher.load_package()

@pytest.fixture
def module():
    import importlib
    return lambda name:importlib.import_module(PACKAGE+'.'+name)
