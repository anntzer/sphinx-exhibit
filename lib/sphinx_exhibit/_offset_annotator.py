import ast
import bisect
import itertools
import tokenize


def iter_attribute_tokens(fname):
    with open(fname, "rb") as file:
        # The call to filter handles cases where an attribute access dot is at
        # the end of a line and the attribute itself on the next one.
        tokens = filter(lambda token: token.string != "\n",
                        tokenize.tokenize(file.readline))
        for token in tokens:
            if token.string == ".":
                yield next(tokens)  # Also catches submodule imports :/


def parse(fname, code_line_idxs):
    attr_tokens = iter_attribute_tokens(fname)

    with tokenize.open(fname) as file:
        source = file.read()

    lines = source.splitlines(keepends=True)
    skipped_line_idxs = {*range(1, len(lines) + 1)}.difference(code_line_idxs)
    for idx in skipped_line_idxs:
        lines[idx - 1] = ""
    line_start_offsets = [
        0, *itertools.accumulate(len(line) for line in lines)]

    def to_offset(lineno, col_offset):
        return line_start_offsets[lineno - 1] + col_offset

    class OffsetAnnotator(ast.NodeVisitor):
        def visit_Name(self, node):
            self.generic_visit(node)
            node.offset = to_offset(node.lineno, node.col_offset)

        def visit_Attribute(self, node):
            self.generic_visit(node)
            while True:
                # Skip spurious ".foo" coming from submodule imports.
                token = next(attr_tokens)
                if node.attr == token.string:
                    break
            node.offset = to_offset(*token.start)

        # These are only necessary to handle fields in the order in which they
        # appear in the source, rather than the order they appear in the node.
        def visit_FunctionDef(self, node):
            for expr in node.decorator_list:
                self.visit(expr)
            self.visit(node.args)
            if node.returns:
                self.visit(node.returns)
            for stmt in node.body:
                self.visit(stmt)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            for expr in node.decorator_list:
                self.visit(expr)
            for expr in node.bases:
                self.visit(expr)
            for keyword in node.keywords:
                self.visit(keyword)
            for stmt in node.body:
                self.visit(stmt)

    mod = ast.parse(source)
    OffsetAnnotator().visit(mod)
    return mod
