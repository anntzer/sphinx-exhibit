import ast
import copy
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
_log = sphinx.util.logging.getLogger(__name__.split(".")[0])


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
    rst.directives.register_directive("exhibit-source", ExhibitSource)
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
            yield ("code", node)


def generate_rst(src_path):
    with tokenize.open(src_path) as file:
        src = file.read()
    paragraphs = []
    block_counter = itertools.count()
    capture_after_lines = []
    for tp, it_group in itertools.groupby(
            _split_strings_and_codes(src), lambda kv: kv[0]):
        it_group = list(item for tp, item in it_group)
        group = "".join(map(str, it_group)).strip()
        if tp == "string":
            paragraphs.append(group)
        elif tp == "code":
            if not group.strip():
                # Don't generate a code-block if the file ends with text.
                continue
            capture_after_lines.append(it_group[-1].get_lineno())
            group = textwrap.indent(group, "   ")
            # TODO Don't duplicate the source, instead run the correct source
            # but after inserting the call to `_sphinx_exhibit_export_` at the
            # ast level... using a custom importer and runpy.run_path.
            paragraphs.append(".. exhibit-block:: {}"
                              .format(next(block_counter)))
            paragraphs.append(group)
        else:
            raise AssertionError
    return (":orphan:\n"
            + "\n"
            + ".. exhibit-source::\n"
            # FIXME Relative path here?
            + "   :source: {}\n".format(src_path)
            + "   :capture-after-lines: {}\n".format(
                " ".join(map(str, capture_after_lines)))
            + "\n"
            + "\n\n".join(paragraphs))


class ExhibitBase(rst.Directive):
    option_spec = {
        "srcdir": rst.directives.unchanged,
        "destdir": rst.directives.unchanged,
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
                 # FIXME Respect suffixes.
                 .with_suffix(".rst"))
                for src_path in src_paths]


class ExhibitAsGenerator(ExhibitBase):
    def run(self):
        for src_path, dest_path in self.get_src_and_dest_paths():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(generate_rst(src_path))
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
            # FIXME Make this configurable?
            plt.close("all")

        # Prevent Matplotlib's cleanup decorator from destroying the
        # warnings filters.
        with warnings.catch_warnings():
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
    app.connect("builder-inited", gen_gallery)
    return {"version": __version__,
            "parallel_read_safe": True,
            "parallel_write_safe": True}
