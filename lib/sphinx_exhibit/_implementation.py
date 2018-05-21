import ast
import itertools
from lib2to3 import pygram
import re
from pathlib import Path
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

from . import _parser, __version__

mpl.backend_bases.FigureManagerBase.show = lambda self: None
plt.switch_backend("agg")


def gen_gallery(app):
    env = BuildEnvironment(app)
    env.find_files(app.config, DummyBuilder(app))
    # Sphinx's registry API warns on overwrite, but we explicitly rely on
    # overwriting the exhibit directive.
    rst.directives.register_directive("exhibit", ExhibitAsGenerator)
    for path in map(Path, map(env.doc2path, env.found_docs)):
        contents = path.read_text()
        directives = re.findall(
            r"(?ms)^\.\.\s+exhibit::\n(?:\s.*\n)+", contents)
        for directive in directives:
            docutils.core.publish_doctree(directive, source_path=path)
    rst.directives.register_directive("exhibit", ExhibitAsRunner)
    rst.directives.register_directive("exhibit-full-source", ExhibitFullSource)
    rst.directives.register_directive("exhibit-block", ExhibitBlock)


def _split_strings_and_codes(src):
    tree = _parser.parse(src)
    for i, node in enumerate(tree.children):
        if (node.type == pygram.python_symbols.simple_stmt
                and node.children[0].type == pygram.token.STRING
                # Exclude b- or f-strings, but not r-strings.
                and not re.search(
                    r"""\A[^'"]*[bBfF]""", node.children[0].value)):
            # This is never the last node.
            tree.children[i + 1].prefix = (
                node.prefix + tree.children[i + 1].prefix)
            yield ("string",
                   ast.literal_eval(
                       "".join(leaf.value for leaf in node.leaves())))
        else:
            yield ("code", str(node))


def generate_rst(src_path):
    with tokenize.open(src_path) as file:
        src = file.read()
    paragraphs = []
    codeblocks = []
    block_counter = itertools.count()
    for tp, it_group in itertools.groupby(
            _split_strings_and_codes(src), lambda kv: kv[0]):
        group = "".join(st for tp, st in it_group).strip()
        if tp == "string":
            paragraphs.append(group)
        elif tp == "code":
            group = textwrap.indent(group, "   ")
            # TODO Don't duplicate the source, instead run the correct source
            # but after inserting the call to `_sphinx_exhibit_export_` at the
            # ast level... using a custom importer and runpy.run_path.
            paragraphs.append(".. exhibit-block:: {}"
                              .format(next(block_counter)))
            paragraphs.append(group)
            codeblocks.append(group)
            codeblocks.append(
                "\n\n"
                "   globals().get('_sphinx_exhibit_export_', lambda: None)()\n")
        else:
            raise AssertionError
    return (":orphan:\n\n"
            + ".. exhibit-full-source::\n\n"
            + "".join(codeblocks)
            + "\n\n"
            + "\n\n".join(paragraphs))


class ExhibitBase(rst.Directive):
    option_spec = {
        "srcdir": rst.directives.unchanged,
        "destdir": rst.directives.unchanged,
    }
    has_content = True

    def get_src_and_dest_paths(self):
        curdir = Path(self.state.document.current_source).parent
        srcdir = curdir / self.options["srcdir"]
        src_paths = []
        for line in self.content:
            if line.startswith("!"):
                for excluded in srcdir.glob(line[1:]):
                    try:
                        src_paths.remove(excluded)
                    except ValueError:
                        pass
            else:
                if line.startswith(r"\!"):
                    line = line[1:]
                src_paths.extend(sorted(srcdir.glob(line)))
        destdir = curdir / self.options["destdir"]
        return [(src_path,
                 # FIXME Respect suffixes.
                 (destdir / src_path.relative_to(srcdir)).with_suffix(".rst"))
                for src_path in src_paths]


class ExhibitAsGenerator(ExhibitBase):
    def run(self):
        for src_path, dest_path in self.get_src_and_dest_paths():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(generate_rst(src_path))
        return []


class ExhibitAsRunner(ExhibitBase):
    def run(self):
        doc_dir = Path(self.state.document.current_source).parent
        vl = ViewList([
            "* :doc:`{}`".format(
                dest_path.relative_to(doc_dir).with_suffix(""))
            for src_path, dest_path in self.get_src_and_dest_paths()
        ])
        node = rst.nodes.Element()
        self.state.nested_parse(vl, 0, node)
        return node.children


class ExhibitFullSource(rst.Directive):
    has_content = True

    def run(self):
        block_counter = itertools.count()

        def _sphinx_exhibit_export_():
            for fig_idx, fignum in enumerate(plt.get_fignums()):
                plt.figure(fignum).savefig("{}-{}-{}.png".format(
                    self.state.document.current_source,
                    next(block_counter),
                    fig_idx))

        # Prevent Matplotlib's cleanup decorator from destrying the
        # warnings filters.
        with warnings.catch_warnings():
            mpl.testing.decorators.cleanup("default")(
                lambda: exec(
                    "\n".join(self.content),
                    {"_sphinx_exhibit_export_": _sphinx_exhibit_export_}))()
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
    app.connect("builder-inited", gen_gallery)
    return {"version": __version__,
            "parallel_read_safe": True,
            "parallel_write_safe": True}
