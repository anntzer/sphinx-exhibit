import contextlib
import os

import matplotlib as mpl
from matplotlib.backend_bases import FigureCanvasBase
from matplotlib.figure import Figure


def item(seq):
    obj, = seq
    return obj


@contextlib.contextmanager
def chdir_cm(path):
    pwd = os.getcwd()
    try:
        os.chdir(str(path))
        yield
    finally:
        os.chdir(pwd)


def thumbnail(in_path, out_path, max_figsize, dpi):
    image = mpl.image.imread(in_path)
    rows, cols, depth = image.shape
    max_width, max_height = max_figsize
    ratio = min(max_width / cols, max_height / rows)
    width = cols * ratio
    height = rows * ratio
    fig = Figure(figsize=(width, height), dpi=dpi)
    FigureCanvasBase(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.imshow(image)
    fig.savefig(out_path, dpi=dpi)
