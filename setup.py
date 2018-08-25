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
    python_requires="",
    setup_requires=["setuptools_scm"],
    use_scm_version=lambda: {  # xref __init__.py
        "version_scheme": "post-release",
        "local_scheme": "node-and-date",
        "write_to": "lib/sphinx_exhibit/_version.py",
    },
    install_requires=[
        "lxml",
        "matplotlib",
        "nbformat",
        "sphinx",
    ],
    entry_points={
        "console_scripts": [],
        "gui_scripts": [],
    },
)
