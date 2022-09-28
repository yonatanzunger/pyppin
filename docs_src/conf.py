# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# http://www.sphinx-doc.org/en/master/config

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import os.path
import sys
from typing import Optional

import sphinx_rtd_theme
from recommonmark.transform import AutoStructify
from sphinx.application import Sphinx

sys.path.insert(0, os.path.abspath("../pyppin"))
sys.path.insert(0, os.path.abspath("."))


# -- Project information -----------------------------------------------------

project = "pyppin"
copyright = "2022, Yonatan Zunger"
author = "Yonatan Zunger"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.coverage",
    # This allows it to parse normal indentation in docstrings.
    "sphinx.ext.napoleon",
    # This allows it to parse .md files as inputs.
    "recommonmark",
    # This lets us link to source code.
    "sphinx.ext.linkcode",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
    "show-inheritance": True,
}

# Obnoxiously, you have to tell sphinx about any sections you want ahead of time,
# or it will just reject them.
napoleon_custom_sections = [
    "Fancier Example",
]


_SRC_ROOT = os.path.abspath("..")


def linkcode_resolve(domain: str, info: dict[str, str]) -> Optional[str]:
    if domain != "py" or not info["module"]:
        return None
    filename = info["module"].replace(".", "/")
    # Is this a directory or a file?
    if os.path.isdir(f"{_SRC_ROOT}/{filename}"):
        filename = filename + "/__init__.py"
    elif os.path.isfile(f"{_SRC_ROOT}/{filename}.py"):
        filename = filename + ".py"
    else:
        return None

    return "https://github.com/yonatanzunger/pyppin/tree/master/" + filename


def setup(app: Sphinx) -> None:
    app.add_config_value(
        "recommonmark_config",
        {"enable_auto_toc_tree": True, "auto_toc_tree_section": "Contents"},
        True,
    )
    app.add_transform(AutoStructify)
