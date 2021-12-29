import os

from setuptools import find_packages, setup

with open(
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md"),
    encoding="utf-8",
) as f:
    long_description = f.read()

setup(
    name="pyppin",
    version="1.0.0",
    description="Python tools collection",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="",  # XXX
    author="",  # XXX
    author_email="",  # XXX
    license="MIT",
    classifiers=[],  # XXX
    project_urls={
        # XXX
    },
    python_requires=">=3.7",
    install_requires=[
        "cachetools",
    ],
    packages=find_packages(exclude=["tests", "tools", "docs", "docs_src"]),
    test_suite="tests",
)
