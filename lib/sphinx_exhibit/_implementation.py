# FIXME: Backreferences (as a rst directive) (perhaps from hunter?).
# FIXME: Generate notebook from the rst-generated html.

import ast
import copy
import itertools
from lib2to3 import pygram
import re
from pathlib import Path
import shutil
import textwrap
import tokenize
import warnings

import docutils
from docutils.parsers import rst
from docutils.statemachine import ViewList
import matplotlib as mpl
import matplotlib.testing.decorators
from matplotlib import pyplot as plt
import sphinx
from sphinx.builders.dummy import DummyBuilder
from sphinx.environment import BuildEnvironment

from . import _parser, _util, __version__

mpl.backend_bases.FigureManagerBase.show = lambda self: None
plt.switch_backend("agg")
_log = sphinx.util.logging.getLogger(__name__.split(".")[0])
_deletion_notice = """\
.. This file was autogenerated by sphinx-exhibit, and will be deleted in the
   next build.

"""


def gen_exhibits(app):
    env = BuildEnvironment(app)
    env.find_files(app.config, DummyBuilder(app))
    # Sphinx's registry API warns on overwrite, but we explicitly rely on
    # overwriting the exhibit directive.
    rst.directives.register_directive("exhibit", ExhibitAsGenerator)
    exhibits = []
    for path in map(Path, map(env.doc2path, env.found_docs)):
        contents = path.read_text()
        if contents.startswith(_deletion_notice):
            path.unlink()
        else:
            exhibits.extend(
                (path, match) for match in re.findall(
                    r"(?ms)^\.\.\s+exhibit::\n(?:\s.*\n)+", contents))
    # Generation must happen after all the unlinking is done.
    for path, match in exhibits:
        docutils.core.publish_doctree(match, source_path=path)
    rst.directives.register_directive("exhibit", ExhibitAsRunner)
    rst.directives.register_directive("exhibit-source", ExhibitSource)
    rst.directives.register_directive("exhibit-block", ExhibitBlock)


def split_text_and_code_blocks(src):
    tree = _parser.parse(src)

    def _inner():
        for i, node in enumerate(tree.children):
            if (node.type == pygram.python_symbols.simple_stmt
                    and node.children[0].type == pygram.token.STRING
                    # Exclude b- or f-strings, but not r-strings.
                    and not re.search(
                        r"""\A[^'"]*[bBfF]""", node.children[0].value)):
                # This is never the last node.
                tree.children[i + 1].prefix = (
                    node.prefix + tree.children[i + 1].prefix)
                yield ("text",
                       ast.literal_eval(
                           "".join(leaf.value for leaf in node.leaves())),
                       node.get_lineno())
            else:
                yield ("code", str(node), node.get_lineno())

    for tp, it_group in itertools.groupby(_inner(), lambda kv: kv[0]):
        _, strs, linenos = zip(*it_group)
        yield tp, "".join(strs), linenos[0]


def generate_rst(src_path, *, sg_style=False):

    if sg_style:
        from sphinx_gallery.py_source_parser import (
            split_code_and_text_blocks as sg_split_text_and_code_blocks)
        _, text_and_code_blocks = sg_split_text_and_code_blocks(src_path)
    else:
        with tokenize.open(src_path) as file:
            src = file.read()
        text_and_code_blocks = split_text_and_code_blocks(src)

    paragraphs = []
    block_counter = itertools.count()
    capture_after_lines = []
    for tp, string, lineno in text_and_code_blocks:
        if tp == "text":
            paragraphs.append(string)
        elif tp == "code":
            if not string.strip():
                # Don't generate a code-block if the file ends with text.
                continue
            capture_after_lines.append(lineno + string.count("\n") - 1)
            paragraphs.append(".. exhibit-block:: {}"
                              .format(next(block_counter)))
            paragraphs.append(textwrap.indent(string, "   "))
        else:
            raise AssertionError

    return (_deletion_notice
            + ":orphan:\n"
            + "\n"
            + ".. exhibit-source::\n"
            # FIXME: Relative path here?
            + "   :source: {}\n".format(src_path)
            + "   :capture-after-lines: {}\n".format(
                " ".join(map(str, capture_after_lines)))
            + "\n"
            + "\n\n".join(paragraphs))


class ExhibitBase(rst.Directive):
    option_spec = {
        "srcdir": rst.directives.unchanged,
        "destdir": rst.directives.unchanged,
        "sphinx-gallery": rst.directives.flag,
    }
    has_content = True

    def get_cur_dir(self):
        return Path(self.state.document.current_source).parent

    def get_src_and_dest_paths(self):
        cur_dir = self.get_cur_dir()
        src_dir = cur_dir / self.options["srcdir"]
        src_paths = []
        for line in self.content:
            if line.startswith("!"):
                excluded = sorted(src_dir.glob(line[1:]))
                _log.info("expanding (for removal) %s to %s.",
                          line, " ".join(str(path.relative_to(src_dir))
                                         for path in excluded))
                for path in excluded:
                    try:
                        src_paths.remove(path)
                    except ValueError:
                        pass
            else:
                if line.startswith(r"\!"):
                    line = line[1:]
                added = sorted(src_dir.glob(line))
                _log.info("expanding (for addition) %s to %s.",
                          line, " ".join(str(path.relative_to(src_dir))
                                         for path in added))
                src_paths.extend(added)
        dest_dir = cur_dir / self.options["destdir"]
        return [(src_path,
                 (dest_dir / src_path.relative_to(src_dir))
                 # FIXME: Respect suffixes.
                 .with_suffix(".rst"))
                for src_path in src_paths]


class ExhibitAsGenerator(ExhibitBase):
    def run(self):
        for src_path, dest_path in self.get_src_and_dest_paths():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(
                generate_rst(
                    src_path, sg_style="sphinx-gallery" in self.options))
            # FIXME: Also arrange to delete this file.
            shutil.copyfile(src_path, dest_path.parent / src_path.name)
        return []


class ExhibitAsRunner(ExhibitBase):
    def run(self):
        cur_dir = self.get_cur_dir()
        vl = ViewList([
            "* :doc:`{}`".format(
                dest_path.relative_to(cur_dir).with_suffix(""))
            for src_path, dest_path in self.get_src_and_dest_paths()
        ])
        node = rst.nodes.Element()
        self.state.nested_parse(vl, 0, node)
        return node.children


class ExhibitSource(rst.Directive):
    option_spec = {
        "source": rst.directives.unchanged,
        "capture-after-lines": rst.directives.positive_int_list,
    }
    has_content = True

    def run(self):
        with tokenize.open(self.options["source"]) as file:
            mod = ast.parse(file.read())
        body = [(stmt.lineno, stmt) for stmt in mod.body]
        inserted = ast.parse("_sphinx_exhibit_export_()").body[0]
        insertions = []
        for lineno in self.options["capture-after-lines"]:
            stmt = copy.deepcopy(inserted)
            ast.increment_lineno(stmt, lineno - 1)
            insertions.append((lineno + .5, stmt))
        mod.body = [stmt for lineno, stmt in sorted(body + insertions,
                                                    key=lambda kv: kv[0])]
        code = compile(mod, self.options["source"], "exec")

        block_counter = itertools.count()

        def _sphinx_exhibit_export_():
            block_idx = next(block_counter)
            for fig_idx, fignum in enumerate(plt.get_fignums()):
                plt.figure(fignum).savefig("{}-{}-{}.png".format(
                    self.state.document.current_source,
                    block_idx, fig_idx))
            # FIXME: Make this configurable?
            plt.close("all")

        # FIXME: chdir is only for SG compatibility.
        # Prevent Matplotlib's cleanup decorator from destroying the warnings
        # filters.
        with _util.chdir_cm(Path(self.options["source"]).parent), \
                warnings.catch_warnings():
            mpl.testing.decorators.cleanup("default")(lambda: exec(
                code, {"_sphinx_exhibit_export_": _sphinx_exhibit_export_}))()
        return []


class ExhibitBlock(rst.Directive):
    required_arguments = 1
    has_content = True

    def run(self):
        dest_and_block = Path("{}-{}".format(
            self.state.document.current_source, self.arguments[0]))
        paths = [path for path in dest_and_block.parent.iterdir()
                 if re.fullmatch(re.escape(dest_and_block.name) + "-\d*.png",
                                 path.name)]
        vl = ViewList([".. code-block:: python", ""]
                      + ["   " + line for line in self.content]
                      + [""]
                      + [".. image:: {}".format(path.name) for path in paths])
        node = rst.nodes.Element()
        self.state.nested_parse(vl, 0, node)
        return node.children


def setup(app):
    app.connect("builder-inited", gen_exhibits)
    return {"version": __version__,
            "parallel_read_safe": True,
            "parallel_write_safe": True}
