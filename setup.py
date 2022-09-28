import os

from setuptools import find_packages, setup

with open(
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "README.md"),
    encoding="utf-8",
) as f:
    long_description = f.read()

setup(
    name="pyppin",
    version="1.0.1",
    description="Python tools collection",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="threading,stack trace,utilities",
    author="Yonatan Zunger",
    author_email="zunger@gmail.com",
    license="MIT",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.7",
    ],
    project_urls={
        "Source": "https://github.com/yonatanzunger/pyppin",
        "Tracker": "https://github.com/yonatanzunger/pyppin/issues",
        "Documentation": "https://yonatanzunger.github.io/pyppin/",
    },
    python_requires=">=3.7",
    install_requires=[],
    packages=find_packages(exclude=["tests", "tools", "docs", "docs_src"]),
    test_suite="tests",
)
