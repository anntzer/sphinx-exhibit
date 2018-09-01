import contextlib
import functools
import inspect
from inspect import Parameter
import os
import sys

from docutils.parsers import rst


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


def directive_runner(
        func=None, *, final_argument_whitespace=False, has_content=False):
    if func is None:
        return functools.partial(
            directive_runner,
            final_argument_whitespace=final_argument_whitespace,
            has_content=has_content)

    sig = inspect.signature(func.__get__(object, object()))
    params = list(sig.parameters.values())
    required_arguments = 0
    optional_arguments = 0
    option_spec = {}
    for param in params:
        if param.kind in (Parameter.POSITIONAL_ONLY,
                          Parameter.POSITIONAL_OR_KEYWORD):
            if param.default is Parameter.empty:
                required_arguments += 1
            else:
                optional_arguments += 1
        elif param.kind is Parameter.KEYWORD_ONLY:
            option_spec[param.name.replace("_", "-")] = lambda arg: arg
        else:
            raise ValueError(
                "Parameter {} is of unsupported kind".format(param))

    cls_vars = sys._getframe().f_back.f_locals
    cls_vars.update(required_arguments=required_arguments,
                    optional_arguments=optional_arguments,
                    final_argument_whitespace=final_argument_whitespace,
                    option_spec=option_spec,
                    has_content=has_content)

    def apply_annotation(param, val):
        return (val if param.annotation is Parameter.empty
                else param.annotation(val))

    def run(self):
        for i in range(len(self.arguments)):
            self.arguments[i] = apply_annotation(params[i], self.arguments[i])
        self.options = {
            k: apply_annotation(sig.parameters[k.replace("-", "_")], v)
            for k, v in self.options.items()}
        return func.__get__(self, type(self))(
            *self.arguments,
            **{k.replace("-", "_"): v for k, v in self.options.items()})

    return run
