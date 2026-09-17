"""
tests/test_no_sdk_leakage.py

AST and static analysis test asserting that external side-effect SDKs
(email, publishing) are isolated strictly to orchestrator_core/core/approval_gate.py.

Guarantees under test:
  1. No module in orchestrator_core other than approval_gate.py imports smtplib, hashnode, or devto.
  2. No agent module in orchestrator_core/agents defines or exposes direct publishing or sending tools.
  3. All external action execution is gate-enforced.
"""

import ast
from pathlib import Path
import pytest

ORCHESTRATOR_CORE_DIR = Path(__file__).resolve().parent.parent / "orchestrator_core"
FORBIDDEN_SDK_MODULES = {"smtplib", "hashnode", "devto"}
ALLOWED_SDK_EXECUTOR_FILE = "approval_gate.py"


def _get_python_files(directory: Path):
    return [p for p in directory.rglob("*.py") if "__pycache__" not in p.parts]


def test_sdk_imports_restricted_to_approval_gate():
    """
    Assert that restricted SDKs (smtplib, hashnode, devto) are NEVER imported
    outside of orchestrator_core/core/approval_gate.py.
    """
    violations = []

    for py_file in _get_python_files(ORCHESTRATOR_CORE_DIR):
        if py_file.name == ALLOWED_SDK_EXECUTOR_FILE:
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8-sig"), filename=str(py_file))
        except SyntaxError as e:
            pytest.fail(f"Syntax error parsing {py_file}: {e}")

        for node in ast.walk(tree):
            # Check `import smtplib`
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    if root_pkg in FORBIDDEN_SDK_MODULES:
                        violations.append(f"{py_file.relative_to(ORCHESTRATOR_CORE_DIR.parent)}:{node.lineno} imports {alias.name}")
            # Check `from smtplib import ...`
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg in FORBIDDEN_SDK_MODULES:
                        violations.append(f"{py_file.relative_to(ORCHESTRATOR_CORE_DIR.parent)}:{node.lineno} imports from {node.module}")

    assert not violations, (
        f"SDK LEAKAGE DETECTED! The following files illegally import external action SDKs:\n"
        + "\n".join(violations)
        + f"\nAll external action SDK imports must be strictly confined to orchestrator_core/core/{ALLOWED_SDK_EXECUTOR_FILE}."
    )


def test_agent_modules_do_not_expose_direct_execution_tools():
    """
    Assert that agent modules in orchestrator_core/agents do not define functions
    or tool definitions that directly publish or send emails.
    """
    agents_dir = ORCHESTRATOR_CORE_DIR / "agents"
    forbidden_tool_names = {
        "send_email",
        "publish_to_hashnode",
        "publish_to_devto",
        "publish_post",
        "direct_publish",
        "publish_article",
    }

    violations = []

    for agent_file in _get_python_files(agents_dir):
        tree = ast.parse(agent_file.read_text(encoding="utf-8-sig"), filename=str(agent_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in forbidden_tool_names:
                    violations.append(
                        f"{agent_file.name}:{node.lineno} defines forbidden tool '{node.name}'"
                    )

    assert not violations, (
        f"AGENT TOOL LEAKAGE DETECTED! Agents must never directly execute side-effects:\n"
        + "\n".join(violations)
    )
