# Contributing to LogicSpace

Please open a [feature request or bug report](https://github.com/Kuattt/LogicSpace-/issues) before a large change. Keep the existing Simulator in engine.py as the source of truth; new hardware and HDL paths should produce actual circuit components and preserve old project JSON.

1. Work on a branch from main. Do not commit .deps, virtual environments, user projects, credentials or generated benchmark data.
2. Keep changes focused and document supported behavior and limitations.
3. Run `PYTHONPATH=.deps python3 -m unittest discover -s tests -q`, `python3 -m py_compile *.py tests/*.py` and `bash -n launch.sh`.
4. For GUI changes, test on Linux with an actual Qt session if possible and say what was not checked.
5. Describe user-visible changes, test results and compatibility effects in the pull request.

The repository currently has no selected project license. Contact the owner before contributing code intended for redistribution; no license is implied by a public repository.
