import contextlib
import os


@contextlib.contextmanager
def chdir_cm(path):
    pwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(pwd)
