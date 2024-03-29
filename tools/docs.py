import copy
import logging
import os
import shutil
import subprocess
import sys
from typing import List

from _common import PACKAGE, REPO_ROOT


def find_command(commandName: str) -> bool:
    return (
        subprocess.run(
            f"which {commandName}", shell=True, stdout=subprocess.DEVNULL
        ).returncode
        == 0
    )


def ensure_requirements() -> bool:
    # Ensure that everything required is installed.
    logging.info("Checking requirements")
    try:
        import recommonmark  # noqa
        import sphinx  # noqa
    except ImportError:
        reqs_file = os.path.abspath(os.path.join(REPO_ROOT, "tools/requirements.txt"))
        rel_path = os.path.relpath(os.getcwd(), reqs_file)
        logging.error(
            f"Required PIP packages are missing. Please run `pip install -r {rel_path}"
        )
        return False

    if not find_command("make"):
        logging.error(
            "make is not installed on your machine! Please ensure you have a working "
            "development environment with all the standard tools."
        )
        return False

    return True


def clear_old_site() -> None:
    logging.info("Clearing old site images")
    shutil.rmtree(os.path.join(REPO_ROOT, "_build"), ignore_errors=True)
    shutil.rmtree(os.path.join(REPO_ROOT, "docs"), ignore_errors=True)


def rebuild_sphinx() -> None:
    # Rebuilds docs/build from docs/. The master config for this is in docs/conf.py and
    # docs/Makefile.
    logging.info("Recompiling HTML from Sphinx")
    # Important trick: Make sure that even if the  package is pip installed, we *don't* use
    # it: instead, 'import <package>' should pull in REPO_ROOT/<package>, so that you build
    # from the current client, not from the last time you ran 'python setup.py install' or the
    # like.
    unwanted = f"site-packages/{PACKAGE}"
    python_path: List[str] = []
    for path_entry in sys.path:
        if unwanted not in path_entry:
            python_path.append(path_entry)
    python_path.append(REPO_ROOT)

    env = copy.copy(os.environ)
    env["PYTHONPATH"] = ":".join(python_path)

    subprocess.run(
        "make html",
        cwd=os.path.join(REPO_ROOT, "docs_src"),
        shell=True,
        check=True,
        env=env,
    )


def configure_site() -> None:
    # While Jekyll would have no problem finding the docs in any directory, the Jekyll that runs as
    # part of GitHub Pages seems a bit more specific.
    shutil.move(
        os.path.join(REPO_ROOT, "docs_src/build/html"), os.path.join(REPO_ROOT, "docs")
    )
    shutil.rmtree(os.path.join(REPO_ROOT, "docs_src/build"))

    with open(os.path.join(REPO_ROOT, "docs/_config.yml"), "w") as jekyll_config:
        jekyll_config.write(
            f"# Config file for Jekyll serving; generated by tools/docs.py\n"
            f"baseurl: /{PACKAGE}\n"
            f"include:\n"
            f"  - /_static\n"
            f"  - /_images\n"
        )


def main() -> None:
    logging.getLogger().addHandler(logging.StreamHandler())
    logging.getLogger().setLevel(logging.INFO)

    if not ensure_requirements():
        return

    clear_old_site()
    rebuild_sphinx()
    configure_site()


if __name__ == "__main__":
    main()
