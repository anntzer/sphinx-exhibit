# Modified from
# https://gist.github.com/FZambia/876b724c329e864b6642adc52b577cdb

from lib2to3 import pygram, pytree
from lib2to3.pgen2.driver import Driver
from lib2to3.pytree import Node, Leaf


def parse(code):
    """String -> AST

    Parse the string and return its AST representation. May raise
    a ParseError exception.
    """
    added_newline = False
    if not code.endswith("\n"):
        code += "\n"
        added_newline = True

    drv = Driver(pygram.python_grammar, pytree.convert)
    result = drv.parse_string(code, True)

    # Always return a Node, not a Leaf.
    if isinstance(result, Leaf):
        result = Node(pygram.python_symbols.file_input, [result])

    result.added_newline = added_newline

    return result


def regenerate(tree):
    """AST -> String

    Regenerate the source code from the AST tree.
    """
    if hasattr(tree, 'added_newline') and tree.added_newline:
        return str(tree)[:-1]
    else:
        return str(tree)
