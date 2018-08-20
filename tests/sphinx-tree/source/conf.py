# -- General configuration ------------------------------------------------

extensions = [
    'sphinx_exhibit',
    'sphinx.ext.intersphinx',
]

source_suffix = '.rst'
master_doc = 'index'

rst_epilog = 'This is the real end.'

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'matplotlib': ('https://matplotlib.org', None),
}
