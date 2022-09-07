import os

from setuptools import find_packages, setup

with open(
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md"),
    encoding="utf-8",
) as f:
    long_description = f.read()

setup(
    name="pyppin",
    version="0.1.0",
    description="Python tools collection",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="",  # TODO
    author="Yonatan Zunger",
    author_email="zunger@gmail.com",
    license="MIT",
    classifiers=[],  # TODO
    project_urls={
        # TODO
    },
    python_requires=">=3.7",
    install_requires=[],
    packages=find_packages(exclude=["tests", "tools", "docs", "docs_src"]),
    test_suite="tests",
)
