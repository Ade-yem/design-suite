#!/usr/bin/env python3
"""
Pre-commit hook for design-suite
Ensures code quality and successful builds before allowing commits.
"""

import subprocess
import sys
import os
from pathlib import Path
from typing import List, Tuple

# ANSI colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"  # No Color

_file_path = Path(__file__).resolve()
if ".git" in _file_path.parts:
    git_idx = _file_path.parts.index(".git")
    PROJECT_ROOT = Path(*_file_path.parts[:git_idx])
else:
    PROJECT_ROOT = _file_path.parent.parent


def run_command(cmd: List[str], cwd: Path | None = None, check: bool = False) -> Tuple[bool, str]:
    """
    Run a shell command and return (success, output).
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def get_staged_files() -> Tuple[List[str], List[str]]:
    """
    Get lists of backend and frontend files that are staged for commit.
    """
    success, output = run_command(["git", "diff", "--cached", "--name-only"])
    if not success:
        return [], []

    staged_files = output.strip().split("\n") if output.strip() else []

    backend_files = [f for f in staged_files if f.startswith("apps/api/")]
    frontend_files = [f for f in staged_files if f.startswith("apps/web/")]

    return backend_files, frontend_files


def check_backend() -> bool:
    """Check backend code quality and tests."""
    print(f"{BLUE}📦 Backend checks (Python){NC}")

    api_dir = PROJECT_ROOT / "apps" / "api"
    errors = []

    # Run pytest
    print("  → Running pytest... ", end="", flush=True)
    venv_pytest = PROJECT_ROOT / "venv" / "bin" / "pytest"
    pytest_cmd = str(venv_pytest) if venv_pytest.exists() else "pytest"
    success, output = run_command([pytest_cmd, "-q", "--tb=short"], cwd=api_dir)
    if success:
        print(f"{GREEN}✓{NC}")
    else:
        print(f"{RED}✗{NC}")
        errors.append(("pytest", output))

    # Type checking with pyright if available
    if (api_dir / "pyrightconfig.json").exists() or (
        api_dir / "pyproject.toml"
    ).exists():
        print("  → Checking type hints... ", end="", flush=True)
        success, output = run_command(["pyright"], cwd=api_dir)
        if success:
            print(f"{GREEN}✓{NC}")
        else:
            # Check if it's just warnings
            if "error" in output.lower():
                print(f"{RED}✗{NC}")
                errors.append(("pyright", output))
            else:
                print(f"{YELLOW}⚠{NC} (warnings found)")

    if errors:
        print(f"\n{RED}Backend check failures:{NC}")
        for check_name, output in errors:
            print(f"\n{check_name}:\n{output}")
        return False

    return True


def check_frontend() -> bool:
    """Check frontend code quality and builds."""
    print(f"{BLUE}📦 Frontend checks (Node.js){NC}")

    web_dir = PROJECT_ROOT / "apps" / "web"
    errors = []

    # Check if dependencies are installed
    node_modules = web_dir / "node_modules"
    if not node_modules.exists():
        print("  ⚠ Dependencies not installed. Installing with pnpm... ", end="", flush=True)
        success, output = run_command(["pnpm", "install"], cwd=web_dir)
        if success:
            print(f"{GREEN}✓{NC}")
        else:
            print(f"{RED}✗{NC}")
            errors.append(("pnpm install", output))
            return False

    # Run ESLint
    print("  → Running ESLint... ", end="", flush=True)
    success, output = run_command(["pnpm", "run", "lint"], cwd=web_dir)
    if success:
        print(f"{GREEN}✓{NC}")
    else:
        print(f"{RED}✗{NC}")
        errors.append(("eslint", output))

    # TypeScript type checking
    print("  → Checking TypeScript... ", end="", flush=True)
    success, output = run_command(["npx", "tsc", "--noEmit"], cwd=web_dir)
    if success:
        print(f"{GREEN}✓{NC}")
    else:
        print(f"{RED}✗{NC}")
        errors.append(("tsc", output))

    if errors:
        print(f"\n{RED}Frontend check failures:{NC}")
        for check_name, output in errors:
            print(f"\n{check_name}:")
            # Limit output to first 40 lines
            lines = output.split("\n")[:40]
            print("\n".join(lines))
            if len(output.split("\n")) > 40:
                print("... (output truncated)")
        return False

    return True


def main() -> int:
    """Run all pre-commit checks."""
    print(f"{BLUE}🔍 Running pre-commit checks...{NC}\n")

    backend_files, frontend_files = get_staged_files()

    if not backend_files and not frontend_files:
        print("No staged files to check (non-source files)")
        return 0

    all_passed = True

    # Run backend checks if there are backend files
    if backend_files:
        if not check_backend():
            all_passed = False
        print()

    # Run frontend checks if there are frontend files
    if frontend_files:
        if not check_frontend():
            all_passed = False
        print()

    # Summary
    if all_passed:
        print(f"{GREEN}✓ All checks passed! Proceeding with commit.{NC}")
        return 0
    else:
        print(f"{RED}✗ Some checks failed. Please fix the errors above before committing.{NC}")
        print(f"{YELLOW}💡 Tip: Use 'git commit --no-verify' to bypass checks (not recommended).{NC}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
