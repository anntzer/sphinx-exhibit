# FIXME: Patch AbstractMovieWriter.saving.
#
# FIXME: Upstream fix to sphinx-jinja.

import ast
from collections import ChainMap, namedtuple
import contextlib
import copy
from enum import Enum
import functools
import html
import itertools
from lib2to3 import pygram
import os
import re
from pathlib import Path
import shutil
import textwrap
import tokenize
from types import BuiltinFunctionType, FunctionType, MethodType, ModuleType
import warnings

import docutils
from docutils.parsers import rst
from docutils.statemachine import ViewList
import lxml.html
import matplotlib as mpl
import matplotlib.testing.decorators
from matplotlib import pyplot as plt
import nbformat.v4
import sphinx
from sphinx.builders.dummy import DummyBuilder
from sphinx.environment import BuildEnvironment
from sphinx.transforms import SphinxTransform

from . import _lib2to3_parser, _offset_annotator, _util, __version__


plt.switch_backend("agg")
_log = sphinx.util.logging.getLogger(__name__.split(".")[0])
_deletion_notice = """\
.. This file was autogenerated by sphinx-exhibit, and will be deleted in the
   next build.
"""


class Stage(Enum):
    RstGeneration, ExampleExecution, ExecutionDone = range(3)


class Style(Enum):
    Native = "native"
    SG = "sphinx-gallery"
    None_ = "none"


State = namedtuple("State", "stage docnames backrefs")


class DocInfo:
    def __init__(self):
        self.src_path = None
        self.code_line_ranges = None
        self.capture_after_lines = []
        self.output_style = None
        self.rst = None
        self.skip = False
        self.outputs = []
        self.artefacts = []
        self.annotations = {}

    def merge(self, other):  # For reloading old info and for parallel builds.
        assert not (self.artefacts and other.artefacts
                    or self.annotations and other.annotations)
        self.artefacts = self.artefacts or other.artefacts
        self.annotations = self.annotations or other.annotations


def builder_inited(app):
    env = BuildEnvironment(app)
    env.exhibit_state = State(Stage.RstGeneration, {}, {})
    env.find_files(app.config, DummyBuilder(app))
    exhibits = []
    for docname in env.found_docs:
        path = Path(env.doc2path(docname))
        contents = path.read_text()
        if contents.startswith(_deletion_notice):
            path.unlink()
    # Generation must happen after all the unlinking is done.
    rst.directives.register_directive("exhibit", Exhibit)
    for docname in env.found_docs:
        path = Path(env.doc2path(docname))
        try:
            contents = path.read_text()
        except FileNotFoundError:  # Could have been deleted just above.
            continue
        if re.search(r"\.\.\s+exhibit::\n", contents):
            # state.document.current_source may lose track of the original
            # document (e.g. when generating contents with .. jinja::), so
            # stash the docname in the env.
            env.prepare_settings(docname)
            # FIXME: Add at least sphinx's default roles.
            # FIXME: Only publish the topmost block containing the exhibit.
            docutils.core.publish_doctree(
                contents, source_path=path, settings_overrides={"env": env})
    app.env.exhibit_prev_state = \
        getattr(app.env, "exhibit_state", State(None, {}, {}))
    app.env.exhibit_state = \
        env.exhibit_state._replace(stage=Stage.ExampleExecution)
    rst.directives.register_directive("exhibit-skip", ExhibitSkip)
    rst.directives.register_directive("exhibit-source", ExhibitSource)
    rst.directives.register_directive("exhibit-block", ExhibitBlock)
    rst.directives.register_directive("exhibit-backrefs", ExhibitBackrefs)
    app.add_node(exhibit_backrefs)
    app.add_post_transform(TransformExhibitBackrefs)


def split_text_and_code_blocks(src):
    tree = _lib2to3_parser.parse(src)  # FIXME: Perhaps rewrite using tokenize.

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
                yield ("code", node, node.get_lineno())

    for tp, it_group in itertools.groupby(_inner(), lambda kv: kv[0]):
        _, strs_or_nodes, linenos = zip(*it_group)
        if tp == "text":
            string = "".join(strs_or_nodes)
        elif tp == "code":
            nodes = [*strs_or_nodes]
            # Extra newlines at the beginning or the end would be dropped
            # during the rst parsing, so drop them.  Also, extra newlines at
            # the beginning would invalidate node.get_lineno().
            nodes[0].prefix = ""
            string = "".join(map(str, nodes)).rstrip("\n") + "\n"
        yield tp, string, linenos[0]


def env_before_read_docs(app, env, docnames):
    for docname, doc_info in env.exhibit_state.docnames.items():
        prev_info = env.exhibit_prev_state.docnames.get(docname)
        if (prev_info
                and doc_info.rst == prev_info.rst
                and all(Path(app.env.srcdir, path).exists()
                        for block in prev_info.artefacts
                        for path in block)):
            doc_info.merge(prev_info)
            docnames.remove(docname)


def doc_info_from_py_source(src_path, *, syntax_style, output_style):

    with src_path.open("rb") as file:
        encoding, _ = tokenize.detect_encoding(file.readline)
    if syntax_style is Style.Native:
        with src_path.open(encoding=encoding) as file:
            src = file.read()
        text_and_code_blocks = split_text_and_code_blocks(src)
    elif syntax_style is Style.SG:
        from sphinx_gallery.py_source_parser import (
            split_code_and_text_blocks as sg_split_text_and_code_blocks)
        _, text_and_code_blocks = sg_split_text_and_code_blocks(src_path)
        # Strip extra newlines at the beginning and the end, as above.  Note
        # that s-g provides a correct lineno including the beginning newlines,
        # so it must be fixed.
        for i in range(len(text_and_code_blocks)):
            tp, string, lineno = text_and_code_blocks[i]
            if tp == "code":
                text_and_code_blocks[i] = (
                    tp,
                    string.strip("\n") + "\n",
                    lineno + len(string) - len(string.lstrip("\n")))
    else:
        assert False

    text_blocks = [
        _deletion_notice,
        ".. raw:: html\n\n"
        "   <p style='text-align:right'><a href='{}' download>"
           "Download this example as Python source.</a></p>\n"
        "   <p style='text-align:right'><a href='{}' download>"
           "Download this example as Jupyter notebook.</a></p>\n"
        "   <div class='sphinx-exhibit-blocks-start'/>"
        .format(html.escape(src_path.name),
                html.escape(src_path.with_suffix(".ipynb").name)),
    ]
    insert_source_block_at = None

    code_line_ranges = []
    capture_after_lines = []
    block_counter = itertools.count()
    for tp, string, lineno in text_and_code_blocks:
        if tp == "text":
            text_blocks.extend([
                string,
                ".. raw:: html\n\n"
                "   <div class='sphinx-exhibit-block-sep' type='text'/>",
            ])
            if insert_source_block_at is None:
                insert_source_block_at = len(text_blocks)
        elif tp == "code":
            if not string.strip():
                # Don't generate a code-block if the file ends with text.
                continue
            if insert_source_block_at is None:
                insert_source_block_at = len(text_blocks)
            n_lines = string.count("\n")
            code_line_ranges.append(range(lineno, lineno + n_lines))
            capture_after_lines.append(lineno + n_lines - 1)
            text_blocks.extend([
                ".. exhibit-block:: {}".format(next(block_counter)),
                textwrap.indent(string, "   "),
                ".. raw:: html\n\n"
                "   <div class='sphinx-exhibit-block-sep' type='code'/>",
            ])
        else:
            assert False

    source_block = (".. exhibit-source::\n" +
                    "   :source: {}\n".format(src_path))
    text_blocks.insert(insert_source_block_at or 0, source_block)

    rst_source = "\n\n".join(text_blocks)
    doc_info = DocInfo()
    doc_info.src_path = src_path
    doc_info.code_line_ranges = code_line_ranges
    doc_info.capture_after_lines = capture_after_lines
    doc_info.output_style = output_style
    doc_info.rst = rst_source
    return doc_info


class SourceGetterMixin(rst.Directive):
    def get_current_source(self):
        env = self.state.document.settings.env
        return Path(env.doc2path(env.docname)).relative_to(env.srcdir)


class Exhibit(SourceGetterMixin):
    option_spec = {
        "srcdir": rst.directives.unchanged_required,
        "destdir": rst.directives.unchanged,
        "syntax-style": Style,
        "output-style": Style,
    }
    has_content = True

    def get_src_paths_and_docnames(self):
        env = self.state.document.settings.env
        cur_dir = self.get_current_source().parent
        src_dir = env.srcdir / cur_dir / self.options["srcdir"]
        src_paths = []
        for line in self.content:
            if line.startswith("!"):
                excluded = sorted(src_dir.glob(line[1:]))
                # Log just once.
                if env.exhibit_state.stage is Stage.RstGeneration:
                    _log.debug("expanding (for removal) %s (in %s) to %s.",
                               line, src_dir.relative_to(env.srcdir),
                               " ".join(str(path.relative_to(src_dir))
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
                # Log just once.
                if env.exhibit_state.stage is Stage.RstGeneration:
                    _log.debug("expanding (for addition) %s (in %s) to %s.",
                               line, src_dir.relative_to(env.srcdir),
                               " ".join(str(path.relative_to(src_dir))
                                        for path in added))
                src_paths.extend(added)
        return [(src_path,
                 Path(cur_dir,
                      self.options["destdir"],
                      src_path.relative_to(src_dir))
                 .with_suffix("").as_posix())
                for src_path in src_paths]

    def run(self):
        env = self.state.document.settings.env

        self.options.setdefault("destdir", os.curdir)
        self.options.setdefault(
            "syntax-style", Style(env.config.exhibit_syntax_style))
        self.options.setdefault(
            "output-style", Style(env.config.exhibit_output_style))

        e_state = env.exhibit_state
        if e_state.stage is Stage.RstGeneration:
            for src_path, docname in self.get_src_paths_and_docnames():
                dest_path = Path(env.doc2path(docname))
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                doc_info = doc_info_from_py_source(
                    src_path,
                    syntax_style=self.options["syntax-style"],
                    output_style=self.options["output-style"])
                dest_path.write_text(doc_info.rst)
                # NOTE: We don't actually need this source; it is only copied
                # for compat with s-g and its use by the .. plot:: directive.
                # FIXME: Also arrange to delete this file.
                shutil.copyfile(src_path, dest_path.parent / src_path.name)
                e_state.docnames[docname] = doc_info
            return []
        else:  # Read stage, either ExampleExecution or ExecutionDone.
            cur_dir = self.get_current_source().parent
            lines = ([".. toctree::",
                      "   :titlesonly:",
                      ""] +
                     ["   /{}".format(docname)
                      for _, docname in self.get_src_paths_and_docnames()])
            node = rst.nodes.Element()
            self.state.nested_parse(ViewList(lines), 0, node)
            return node.children


class ExhibitSkip(SourceGetterMixin):
    def run(self):
        env = self.state.document.settings.env
        doc_info = env.exhibit_state.docnames[env.docname]
        doc_info.skip = True
        return []


DocRef = namedtuple("DocRef", "role lookups")
Annotation = namedtuple("Annotation", "docrefs href")


def get_docref(obj, source_name, parent=None):
    if isinstance(parent, ModuleType):
        if hasattr(obj, "__name__") and obj.__name__ != source_name:
            return None
        return DocRef("any", (parent.__name__ + "." + source_name,))
    if not hasattr(obj, "__name__") or obj.__name__ != source_name:
        return None
    if isinstance(obj, ModuleType):
        return DocRef("py:module", (obj.__name__,))
    if not (hasattr(obj, "__module__") and hasattr(obj, "__qualname__")):
        return None
    lookups = ((obj.__module__ + "." + obj.__qualname__, obj.__qualname__)
               if obj.__module__ is not None
               # Happens with extension functions, e.g. RandomState.seed.
               else (obj.__qualname__,))
    if isinstance(obj, type):
        return DocRef("py:class", lookups)
    elif (isinstance(obj, (FunctionType, BuiltinFunctionType))
          and "." not in obj.__qualname__):
        return DocRef("py:function", lookups)
    elif isinstance(obj, (MethodType, FunctionType, BuiltinFunctionType)):
        # Bound and unbound methods, also (bound) classmethods and
        # staticmethods (roles added by resolve_annotation).
        return DocRef("py:method", lookups)
    else:
        raise TypeError(
            "Named module-level object of unknown type: {!r}".format(obj))


class ExhibitSource(SourceGetterMixin):
    option_spec = {
        "source": rst.directives.unchanged_required,
    }
    has_content = True

    @staticmethod
    @contextlib.contextmanager
    def _patch_mpl_interactivity():
        FigureCanvasBase = mpl.backend_bases.FigureCanvasBase
        FigureManagerBase = mpl.backend_bases.FigureManagerBase
        start_event_loop = FigureCanvasBase.start_event_loop
        show = mpl.backend_bases.FigureManagerBase.show
        FigureCanvasBase.start_event_loop = lambda self, timeout=0: None
        FigureManagerBase.show = lambda self: None
        try:
            yield
        finally:
            FigureCanvasBase.start_event_loop = start_event_loop
            FigureManagerBase.show = show

    def run(self):
        env = self.state.document.settings.env
        if env.exhibit_state.stage is Stage.ExecutionDone:
            _log.warning(
                "Handling %s after docrefs have already been resolved.")

        doc_info = env.exhibit_state.docnames[env.docname]
        doc_info.artefacts = [[] for _ in doc_info.capture_after_lines]
        doc_info.outputs = ["" for _ in doc_info.capture_after_lines]
        if doc_info.skip or doc_info.output_style is Style.None_:
            return []

        mod = _offset_annotator.parse(
            self.options["source"],
            [idx for code_line_range in doc_info.code_line_ranges
             for idx in code_line_range])

        # Rewrite (Load context only):
        # - foo
        #   -> _sphinx_exhibit_name_(foo, "foo", offset)
        # - foo.bar
        #   -> _sphinx_exhibit_attr_(foo, "bar", offset)

        name_func_name = "!sphinx_exhibit_name"
        attr_func_name = "!sphinx_exhibit_attr"
        export_func_name = "!sphinx_exhibit_export"

        class Transformer(ast.NodeTransformer):
            def visit_Name(self, node):
                return (
                    ast.fix_missing_locations(ast.copy_location(
                        ast.Call(
                            ast.Name(name_func_name, ast.Load()),
                            [node, ast.Str(node.id), ast.Num(node.offset)],
                            []),
                        node))
                    if type(node.ctx) == ast.Load else
                    node)

            def visit_Attribute(self, node):
                self.generic_visit(node)
                return (
                    ast.fix_missing_locations(ast.copy_location(
                        ast.Call(
                            ast.Name(attr_func_name, ast.Load()),
                            [node.value, ast.Str(node.attr), ast.Num(node.offset)],
                            []),
                        node))
                    if type(node.ctx) == ast.Load else
                    node)

        mod = Transformer().visit(mod)

        for lineno in doc_info.capture_after_lines:
            inserted = ast.fix_missing_locations(
                ast.Expr(
                    ast.Call(
                        ast.Name(export_func_name, ast.Load()),
                        [], []),
                    lineno=lineno))
            mod.body.append(inserted)
        mod.body.sort(key=lambda stmt: stmt.lineno)
        code = compile(mod, self.options["source"], "exec")

        def sphinx_exhibit_name(obj, name, offset):
            docref = get_docref(obj, name)
            if docref:
                (doc_info.annotations
                 .setdefault(offset, Annotation(set(), None))
                 .docrefs.add(docref))
            return obj

        def sphinx_exhibit_attr(obj, name, offset):
            attr = getattr(obj, name)
            docref = get_docref(attr, name, parent=obj)
            if docref:
                (doc_info.annotations
                 .setdefault(offset, Annotation(set(), None))
                 .docrefs.add(docref))
            return attr

        block_idx = 0
        sg_base_num = 0
        def sphinx_exhibit_export():
            nonlocal block_idx, sg_base_num
            for fig_idx, fignum in enumerate(plt.get_fignums()):
                if doc_info.output_style is Style.Native:
                    dest = Path(
                        env.srcdir,
                        "{}-{}-{}.png".format(env.docname, block_idx, fig_idx))
                elif doc_info.output_style is Style.SG:
                    dir_path = (env.srcdir
                                / self.get_current_source().parent
                                / "images")
                    dir_path.mkdir(exist_ok=True)
                    dest = Path(
                        dir_path / "sphx_glr_{}_{:03}.png".format(
                            Path(env.docname).name, sg_base_num + fignum))
                else:
                    assert False
                doc_info.artefacts[block_idx].append(
                    dest.relative_to(env.srcdir))
                plt.figure(fignum).savefig(dest)
            block_idx += 1
            sg_base_num += len(plt.get_fignums())
            # FIXME: Make this configurable?
            plt.close("all")

        class Stream:
            def __init__(self):
                self._writes = [[] for _ in range(len(doc_info.outputs))]

            def write(self, s):
                self._writes[block_idx].append(s)

            def get_contents(self):
                return ["".join(block) for block in self._writes]

        stream = Stream()

        # FIXME: chdir is only for s-g compatibility.
        # FIXME: Also patch sys.argv.
        # FIXME: runpy + override source_to_code in a custom importer.
        # Prevent Matplotlib's cleanup decorator from destroying the warnings
        # filters.
        with self._patch_mpl_interactivity(), \
                _util.chdir_cm(Path(self.options["source"]).parent), \
                warnings.catch_warnings(), \
                contextlib.redirect_stdout(stream), \
                contextlib.redirect_stderr(stream):
            try:
                mpl.testing.decorators.cleanup("default")(lambda: exec(
                    code,
                    {name_func_name: sphinx_exhibit_name,
                     attr_func_name: sphinx_exhibit_attr,
                     export_func_name: sphinx_exhibit_export,
                     "__file__": self.options["source"],
                     "__name__": "__main__"}))()
            except (Exception, SystemExit) as e:
                _log.warning("%s raised %s: %s", env.docname, type(e), e)

        doc_info.outputs = stream.get_contents()

        return []


class ExhibitBlock(SourceGetterMixin):
    required_arguments = 1
    has_content = True

    def run(self):
        env = self.state.document.settings.env
        doc_info = env.exhibit_state.docnames[env.docname]
        current_source = self.get_current_source()
        lines = ([".. code-block:: python", ""] +
                 ["   " + line for line in self.content] +
                 [""])
        block_idx = int(self.arguments[0])
        lines.extend([
            ".. raw:: html",
            "",
            "   <div class='sphinx-exhibit-nbskip'>",
            "",
        ])
        if doc_info.outputs[block_idx]:
            lines.extend([
                ".. code-block:: none",
                ""] + [
                "   " + line
                for line in doc_info.outputs[block_idx].splitlines()
            ])
        for path in doc_info.artefacts[block_idx]:
            lines.extend([
                ".. image:: {}".format(
                    path.relative_to(current_source.parent)),
                "   :align: center",
                "",
            ])
        lines.extend([
            ".. raw:: html",
            "",
            "   </div>",
            "",
        ])
        node = rst.nodes.Element()
        self.state.nested_parse(ViewList(lines), 0, node)
        return node.children


@functools.lru_cache()
def resolve_docrefs(env):
    """
    Resolve the runtime annotations.

    After this step, resolved annotations contain a single DocRef which
    contains a single lookup.
    """
    env.exhibit_state = env.exhibit_state._replace(stage=Stage.ExecutionDone)

    # Construct the merged inventory.
    inv = {}
    py_domain = "py"
    # Adapted from InventoryFile.{dump,load_v2}.
    for name, dispname, role, docname, anchor, prio \
            in sorted(env.domains[py_domain].get_objects()):
        uri = env.app.builder.get_target_uri(docname)
        if anchor:
            uri += "#" + anchor
        inv.setdefault(py_domain + ":" + role, {})[name] = name, uri
    if "sphinx.ext.intersphinx" in env.config.extensions:
        for role, role_inv in env.intersphinx_inventory.items():
            inv[role] = ChainMap(
                inv.get(role, {}),
                {name: (name, uri)
                 for name, (project, version, uri, dispname)
                 in role_inv.items()})
    for role, role_inv in inv.items():
        suffixes_role_inv = {}
        for k, v in role_inv.items():
            parts = k.split(".")
            for i in range(len(parts)):
                suffixes_role_inv.setdefault(".".join(parts[i:]), []).append(v)
        inv[role] = ChainMap(
            role_inv,
            # Only keep unambiguous suffixes.
            {suffix: _util.item(vs) for suffix, vs in suffixes_role_inv.items()
             if len(vs) == 1})

    def resolve_annotation(annotation):
        if len(annotation.docrefs) == 1:  # Otherwise, would be ambiguous.
            docref, = annotation.docrefs

            if docref.role == "any":
                roles = inv
            elif docref.role == "py:method":
                roles = ["py:method", "py:classmethod", "py:staticmethod"]
            else:
                roles = [docref.role]

            def lookup_by_role(role):
                role_inv = inv.get(role, {})
                for lookup in docref.lookups:
                    try:
                        true_lookup, uri = role_inv[lookup]
                    except KeyError:
                        continue
                    return annotation._replace(
                        docrefs={
                            docref._replace(
                                role=role, lookups=(true_lookup,))},
                        href=uri)

            candidates = list(filter(None,
                                     (lookup_by_role(role) for role in roles)))
            if len(candidates) == 1:
                return _util.item(candidates)
        return annotation

    # Resolve the docrefs.
    for docname, doc_info in env.exhibit_state.docnames.items():
        for offset, annotation in doc_info.annotations.items():
            if len(annotation.docrefs) == 1:  # Other annots. are ambiguous.
                docref, = annotation.docrefs
                doc_info.annotations[offset] = resolve_annotation(annotation)


@functools.lru_cache()
def compute_backrefs(env):
    for docname, doc_info in env.exhibit_state.docnames.items():
        for annotation in doc_info.annotations.values():
            if annotation.href:  # Resolved, so single values below.
                docref, = annotation.docrefs
                lookup, = docref.lookups
                (env.exhibit_state.backrefs
                 .setdefault((docref.role, lookup), set())
                 .add(docname))


class exhibit_backrefs(rst.nodes.Element):
    pass


class ExhibitBackrefs(rst.Directive):
    required_arguments = 2
    option_spec = {
        "title": rst.directives.unchanged,
    }

    def run(self):
        role, name = self.arguments
        title = self.options.get("title", "")
        # Parse the title now that this can easily be done, and remove it later
        # if it turns out to be unneeded.
        node = rst.nodes.Element()
        self.state.nested_parse(ViewList([title]), 0, node)
        return (node.children
                + [exhibit_backrefs(role=role, name=name,
                                    title_node_count=len(node.children))])


class TransformExhibitBackrefs(SphinxTransform):
    default_priority = 400

    def apply(self):
        resolve_docrefs(self.env)
        compute_backrefs(self.env)

        class ExhibitBackrefsVisitor(rst.nodes.SparseNodeVisitor):
            def visit_exhibit_backrefs(_, node):
                # FIXME: Directly build the docutils tree.  (Tried...)
                backrefs = sorted(
                    self.env.exhibit_state.backrefs.get(
                        (node.attributes["role"], node.attributes["name"]),
                        []))
                if backrefs:
                    bullets = []
                    titles = []
                    hrefs = []
                    for idx, docname in enumerate(backrefs):
                        title = self.env.titles[docname][0].rawsource
                        html_fname = ("../" * self.env.docname.count("/")
                                    + docname + self.app.builder.out_suffix)
                        bullets.append("- |id{}|__\n".format(idx))
                        titles.append(".. |id{}| replace:: {}\n"
                                      .format(idx, title))
                        hrefs.append("__ {}\n".format(html_fname))
                    new = docutils.core.publish_doctree(
                        "".join(bullets) + "\n" +
                        "".join(titles) + "\n" +
                        "".join(hrefs))
                    node.replace_self(new.children)
                else:
                    title_node_count = node.attributes["title_node_count"]
                    remove_from_idx = (
                        node.parent.index(node) - title_node_count)
                    for idx in range(title_node_count + 1):
                        node.parent.pop(remove_from_idx)

        self.document.walkabout(ExhibitBackrefsVisitor(self.document))


def env_merge_info(app, env, docnames, other):
    for path, other_info in other.exhibit_state.paths.items():
        info = env.state.exhibit_state.paths[path]
        info.merge(other_info)


def build_finished(app, exc):
    if exc or app.builder.name != "html":  # s-g also whitelists "readthedocs"?
        return
    docnames = app.env.exhibit_state.docnames
    iter_docnames = functools.partial(sphinx.util.status_iterator, docnames,
                                      length=len(docnames))
    for docname in iter_docnames("copying exhibit sources and notebooks... "):
        copy_py_source(app, docname)
        generate_notebook(app, docname)
    for docname in iter_docnames("embedding links... "):
        embed_annotations(app, docname)


def copy_py_source(app, docname):
    shutil.copyfile(
        app.env.exhibit_state.docnames[docname].src_path,
        Path(app.builder.get_outfilename(docname)).with_suffix(".py"))


def generate_notebook(app, docname):
    doc_info = app.env.exhibit_state.docnames[docname]
    source_lines = [
        None, *doc_info.src_path.read_text().splitlines(keepends=True)]
    code_blocks = ("".join(source_lines[idx] for idx in code_block)
                   for code_block in doc_info.code_line_ranges)
    cells = []

    html_path = Path(app.builder.get_outfilename(docname))
    root = lxml.html.parse(str(html_path)).getroot()
    for elem in root.findall(".//a[@class='headerlink']"):
        elem.getparent().remove(elem)
    for elem in root.findall(".//div[@class='sphinx-exhibit-nbskip']"):
        elem.getparent().remove(elem)

    elem, = root.findall(".//div[@class='sphinx-exhibit-blocks-start']")
    assert elem.tail is None
    parent = elem.getparent()
    parent[:parent.index(elem) + 1] = []
    elem = parent
    while True:
        parent = elem.getparent()
        if parent is None:
            break
        parent[:parent.index(elem)] = []
        elem = parent

    while True:
        elem = root.find(".//div[@class='sphinx-exhibit-block-sep']")
        if elem is None:
            break
        assert elem.tail is None
        etype = elem.attrib["type"]
        remainder = copy.deepcopy(root)
        # In the block, delete everything from the sep.
        parent = elem.getparent()
        parent[parent.index(elem):] = []
        elem = parent
        while True:
            parent = elem.getparent()
            if parent is None:
                break
            parent[parent.index(elem) + 1:] = []
            elem = parent
        if etype == "text":
            rendered = lxml.etree.tostring(root).decode("utf-8")
            # Remove blank lines, as they are insignificant and cause md to
            # treat following indented lines as blocks.
            rendered = "\n".join(
                line for line in rendered.splitlines() if line.strip())
            cells.append(nbformat.v4.new_markdown_cell(rendered))
        elif etype == "code":
            # Remove trailing newlines, as nbformat renders even a single final
            # newline as a blank line.
            cells.append(nbformat.v4.new_code_cell(
                next(code_blocks).rstrip("\n")))
        # In the remainder tree, delete everything up to and including the sep.
        root = remainder
        # The same elem as above, but in the remainder tree.
        elem = root.find(".//div[@class='sphinx-exhibit-block-sep']")
        parent = elem.getparent()
        parent[:parent.index(elem) + 1] = []
        elem = parent
        while True:
            parent = elem.getparent()
            if parent is None:
                break
            parent[:parent.index(elem)] = []
            elem = parent

    notebook = nbformat.v4.new_notebook(cells=cells)
    with html_path.with_suffix(".ipynb").open("w") as file:
        nbformat.write(notebook, file)


def embed_annotations(app, docname):
    html_path = Path(app.builder.get_outfilename(docname))
    annotations = app.env.exhibit_state.docnames[docname].annotations

    rel_prefix = "../" * (len(html_path.relative_to(app.outdir).parents) - 1)
    def fix_rel_href(href):
        if "://" not in href:
            href = rel_prefix + href
        return href

    tree = lxml.html.parse(str(html_path))
    elems = tree.findall(
        ".//div[@class='highlight-python notranslate']/div/pre")
    offset = 0
    offset_to_elem = {}

    def visit(elem):
        nonlocal offset
        offset_to_elem[offset] = elem
        offset += len(elem.text or "")
        for child in elem:
            visit(child)
        offset += len(elem.tail or "")

    for elem in elems:
        visit(elem)

    for offset, annotation in annotations.items():
        try:
            elem = offset_to_elem[offset]
            expected_prefix = ""
        except KeyError:
            # Should be a decorator.
            # NOTE: Although the grammar theoretically allows whitespace after
            # the "@", this is never seen in practice and more importantly not
            # parsed correctly by pygments anyways.
            try:
                elem = offset_to_elem[offset - 1]
                expected_prefix = "@"
            except KeyError:
                _log.warning(  # Can happen with composite decorators...
                    "In {}, dropping annotation {} not matching highlighting "
                    "at offset {}.".format(docname, annotation, offset),
                    type="sphinx-exhibit", subtype="embedding")
                continue

        if not annotation.href:
            continue
        assert elem.text == (
            expected_prefix
            + _util.item(_util.item(annotation.docrefs).lookups)
              .split(".")[-1])
        link = lxml.html.Element("a", href=fix_rel_href(annotation.href))
        link.text = elem.text
        elem.text = ""
        elem.append(link)

    tree.write(str(html_path))


def setup(app):
    # These affect rst generation but don't invalidate previous parses.
    app.add_config_value("exhibit_syntax_style", "native", "")
    app.add_config_value("exhibit_output_style", "native", "")
    app.connect("builder-inited", builder_inited)
    app.connect("env-before-read-docs", env_before_read_docs)
    app.connect("env-merge-info", env_merge_info)
    app.connect("build-finished", build_finished)
    return {"version": __version__,
            "env_version": 0,
            "parallel_read_safe": True,
            "parallel_write_safe": True}
