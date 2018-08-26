from setupext import find_packages, setup


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
    packages=find_packages("lib"),
    package_dir={"": "lib"},
    ext_modules=[],
    package_data={},
    python_requires=">=3.5",
    setup_requires=["setuptools_scm"],
    use_scm_version=lambda: {  # xref __init__.py
        "version_scheme": "post-release",
        "local_scheme": "node-and-date",
        "write_to": "lib/sphinx_exhibit/_version.py",
    },
    install_requires=[
        "lxml>=3.5",  # First to support Py3.5.
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
