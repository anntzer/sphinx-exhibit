import ast
import bisect
import itertools
import tokenize


def iter_attribute_tokens(fname):
    with open(fname, "rb") as file:
        tokens = tokenize.tokenize(file.readline)
        for token in tokens:
            if token.string == ".":
                yield next(tokens)


def parse(fname):
    attr_tokens = iter_attribute_tokens(fname)

    with tokenize.open(fname) as file:
        source = file.read()

    line_start_idxs = [
        0, *itertools.accumulate(map(len, source.splitlines(keepends=True)))]

    def to_offset(lineno, col_offset):
        return line_start_idxs[lineno - 1] + col_offset

    class OffsetAnnotator(ast.NodeVisitor):
        def visit_Name(self, node):
            self.generic_visit(node)
            node.offset = to_offset(node.lineno, node.col_offset)

        def visit_Attribute(self, node):
            self.generic_visit(node)
            token = next(attr_tokens)
            node.offset = to_offset(*token.start)

    mod = ast.parse(source)
    OffsetAnnotator().visit(mod)
    return mod
