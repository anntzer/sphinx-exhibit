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


def ensure_contents(path, contents):
    if not (path.exists() and path.read_text() == contents):
        path.write_text(contents)
