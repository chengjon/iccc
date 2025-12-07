"""Software development workflow templates."""

import sys
from pathlib import Path

from iccc.planning.templates.feature_development import (
    create_feature_development_method,
    create_feature_tasks,
)
from iccc.planning.templates.bug_fix import (
    create_bug_fix_method,
    create_bug_fix_tasks,
)
from iccc.planning.templates.refactoring import (
    create_refactoring_method,
    create_refactoring_tasks,
)

# Import TaskDecomposer from the templates.py module file
# We need to import from parent directory iccc.planning
import importlib.util

_templates_py = Path(__file__).parent.parent / "templates.py"
_spec = importlib.util.spec_from_file_location("iccc.planning._templates_module", _templates_py)
if _spec and _spec.loader:
    _templates_module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_templates_module)
    TaskDecomposer = _templates_module.TaskDecomposer
else:
    TaskDecomposer = None  # type: ignore

__all__ = [
    "create_feature_development_method",
    "create_feature_tasks",
    "create_bug_fix_method",
    "create_bug_fix_tasks",
    "create_refactoring_method",
    "create_refactoring_tasks",
    "TaskDecomposer",
]
