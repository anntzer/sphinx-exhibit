import contextlib
import os


def item(seq):
    obj, = seq
    return obj


@contextlib.contextmanager
def chdir_cm(path):
    pwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(pwd)
