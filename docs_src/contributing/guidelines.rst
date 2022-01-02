Contribution Guidelines
-----------------------

pyppin is very open to contributions to the library. In general, a good function to add to pyppin
should be something broadly applicable to Python development (rather than specific to a narrow range
of uses), and not have substantial external dependencies. As a good rule of thumb, if the only
reason the thing you're adding isn't a good candidate for the Python standard library is that
there's no strong reason to add the maintenance burden of adding it _to_ the standard library, and
the thing isn't big enough to merit its own pip package, this is probably a good place for it.

pyppin does not make any attempt to support Python 2, but it does not make assertions about specific
versions beyond that.

All code within pyppin should be thoroughly unittested and fully type-annotated. Both tests and the
linter can be invoked using ``tox``; you can manually invoke the lint autoformatter by running
``python tools/lint.py --fix``. The lint pass includes mypy and must run without errors.

Code should be extensively commented. Functions and classes should generally have docstrings in
RST-compatible (`PEP 287<https://www.python.org/dev/peps/pep-0287/>`) format. Within the code,
implementation comments should err on the side of detail: good pyppin code should be usable as
teaching examples, illustrating good Python style and clear explanations of nuance.

If you update the documentation (either anything in ``docs_src/`` or any docstrings), you can
regenerate the actual docs by running ``python tools/docs.py``. This requires that you have the
requirements in ``tools/`` and ``docs_src`` installed in your Python environment; the resulting
files should be part of your changelist.
