from lib2to3 import pygram, pytree
from lib2to3.pgen2.driver import Driver
from lib2to3.pytree import Node, Leaf


def parse(code):
    """String -> AST

    Parse the string and return its AST representation. May raise
    a ParseError exception.
    """
    # Modified from
    # https://gist.github.com/FZambia/876b724c329e864b6642adc52b577cdb
    drv = Driver(pygram.python_grammar, pytree.convert)
    result = drv.parse_string(code + "\n", True)
    if isinstance(result, Leaf):  # Always return a Node, not a Leaf.
        result = Node(pygram.python_symbols.file_input, [result])
    # Could track whether str() needs to remove the newline, but not worth it.
    return result
