import importlib.metadata

from ._implementation import setup


try:
    __version__ = importlib.metadata.version("sphinx_exhibit")
except ImportError:
    __version__ = "0+unknown"

__all__ = ["setup"]
