import contextlib
import shutil
import subprocess
import sys
from pathlib import Path


def test_run():
    for to_clean in ["source/examples", "build"]:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(
                str(Path(__file__).parent / "sphinx-tree" / to_clean))
    subprocess.run(
        [sys.executable, "-msphinx", "-M", "html", "source", "build", "-T"],
        cwd=str(Path(__file__).parent / "sphinx-tree"),
        check=True)
