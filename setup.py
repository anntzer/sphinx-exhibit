# find_namespace_packages itself bounds support to setuptools>=40.1.
from setuptools import find_namespace_packages, setup


setup(
    name="sphinx_exhibit",
    description="",
    long_description=open("README.rst", encoding="utf-8").read(),
    author="Antony Lee",
    author_email="",
    url="",
    license="MIT",
    classifiers=[],
    py_modules=[],
    packages=find_namespace_packages("lib"),
    package_dir={"": "lib"},
    ext_modules=[],
    package_data={},
    python_requires=">=3.8",
    setup_requires=["setuptools_scm"],
    use_scm_version=lambda: {  # xref __init__.py
        "version_scheme": "post-release",
        "local_scheme": "node-and-date",
    },
    install_requires=[
        "lxml",  # Bounded by Py3.8 support.
        "matplotlib>=2.0",  # Changed mpl.testing.decorators.cleanup.
        "nbformat>=4.0",
        "sphinx>=1.7",  # BuildEnvironment.prepare_settings.
        # Depends on nose on "old-enough" matplotlibs.
    ],
    entry_points={
        "console_scripts": [],
        "gui_scripts": [],
    },
)
