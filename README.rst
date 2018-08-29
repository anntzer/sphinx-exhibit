Showcase examples in Sphinx-generated documentation
===================================================

This Sphinx extension introduces a ``.. exhibit::`` directive that can be used
to generate one page per example in a Sphinx-generated documentation.

Activate by adding ``"sphinx_exhibit"`` in the list of extensions in your
``conf.py``.  Then, in one of your rst sources, add e.g.

.. code-block:: rst

   .. exhibit::
      :srcdir: ../examples
      :destdir: examples

      this_example_comes_first.py
      *.py

This will look up examples in ``srcdir`` (here, ``../examples``; relative to
the directory of the rst source), and create a rst example file for each of
the files listed, in ``destdir`` (again relative to the directory of the rst
source; defaults to ``.`` if not given). Globbing syntax can be used, and
examples listed before the glob will not be duplicated (but stay in front).

Multi-block examples can use Sphinx-Gallery's syntax ("special comments"); or,
later blocks can just be introduced as top-level strings (i.e., as if they were
mid-program docstrings).  The latter format is the default; Sphinx-Gallery's
format can be activated with the ``:syntax-style: sphinx-gallery`` option, or
globally in ``conf.py`` with ``exhibit_syntax_style = "sphinx-gallery"``).
Note that this option depends on Sphinx-Gallery being installed (we reuse its
parser in that case).

By default, output images are named ``{filename}-{block_idx}-{figure_idx}.png``
(both indices start at zero).  Sphinx-Gallery-style numbering can likewise be
activated with ``:output-style: sphinx-gallery`` / ``exhibit_output_style =
"sphinx-gallery"``.

The *topmost* docstring can contain the ``.. exhibit-skip::`` directive (which
takes no arguments and generates no output); if it is found there, the code
will not be run.

The list of examples that use a specific API element can be output using the
``.. exhibit-backrefs::`` directive, whose syntax is

.. code-block:: rst

   .. exhibit-backrefs:: role qualified.name
      :title: ...

where the optional ``:title:`` is printed before the list if there is at least
one of them.

Development notes
-----------------

Sphinx-Exhibit uses its ``__version__`` (which comes from ``git describe
-a``) as the environment version reported to Sphinx.  To prevent invalidation
of an environment generated with a previous ``__version__``, set the
``SPHINX_EXHIBIT_ENV_VERSION`` environment variable to the desired value.  Of
course, things may not go so well if the format of the data stored internally
by Sphinx-Exhibit *did* change.
