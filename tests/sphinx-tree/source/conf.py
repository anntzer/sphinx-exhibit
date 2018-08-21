# -- General configuration ------------------------------------------------

extensions = [
    'sphinx_exhibit',
    'sphinx.ext.intersphinx',
]

source_suffix = '.rst'
master_doc = 'index'

rst_epilog = 'This is the real end.'

intersphinx_mapping = {
    'matplotlib': ('https://matplotlib.org', None),
}
