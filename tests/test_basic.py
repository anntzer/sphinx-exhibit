import subprocess
import sys
from pathlib import Path


def test_run():
    subprocess.run(
        [sys.executable, "-msphinx", "-M", "html", "source", "build"],
        cwd=Path(__file__).parent / "sphinx-tree",
        check=True)
