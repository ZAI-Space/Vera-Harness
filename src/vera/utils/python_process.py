"""Launch trusted Python modules without implicitly importing project-local code."""

import sys

_MODULE_BOOTSTRAP = """import sys
if sys.path and sys.path[0] == "":
    sys.path.pop(0)
import runpy
runpy.run_module(sys.argv.pop(1), run_name="__main__", alter_sys=True)
"""


def python_module_command(module: str, *arguments: str) -> list[str]:
    """Build an argv for a trusted worker without changing its working directory.

    Unlike ``python -m``, the bootstrap removes the interpreter's implicit cwd
    search entry before importing the module. Explicit PYTHONPATH and installed
    packages remain available; callers must supply trusted import paths. Module
    arguments retain their order. This also works on Python 3.10, before ``-P``.
    """
    return [sys.executable, "-c", _MODULE_BOOTSTRAP, module, *arguments]
