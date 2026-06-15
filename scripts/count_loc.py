#!/usr/bin/env python3
"""Project Lines of Code (LOC) Counter.

This module provides a production-grade utility to scan the repository,
categorize files into frontend and backend applications, filter files
based on `.gitignore` specifications (using git directly or a manual fallback),
and count total, code, blank, and comment lines of code.

Performance & Scale Considerations:
1. Memory Usage: Files are read line-by-line lazily using Python's generator
   pipeline, avoiding loading entire files into memory.
2. Large Files: Files exceeding 10MB are automatically skipped to prevent
   unnecessary I/O overhead.
3. Unicode Safety: Standard UTF-8 is used, falling back to 'latin-1' or
   skipping the file entirely on failure (e.g., binary files).
4. Subprocess Limits: Git commands are executed once to retrieve the full list of
   tracked/untracked files, minimizing process creation overhead.
"""

import argparse
import dataclasses
import fnmatch
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, List, Optional, Set, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("loc_counter")

# Limit scanning file size (10 MB) to prevent locking on large data files
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Mapping of file extensions to their comment styles
COMMENT_STYLES: Dict[str, str] = {
    ".py": "hash",
    ".js": "slash",
    ".jsx": "slash",
    ".ts": "slash",
    ".tsx": "slash",
    ".css": "css",
    ".html": "html",
    ".sql": "sql",
    ".yaml": "hash",
    ".yml": "hash",
    ".toml": "hash",
    ".json": "none",
}


@dataclass(frozen=True)
class FileStats:
    """Statistics for a single file.

    Attributes:
        file_path: Relative path to the file.
        extension: Lowercase file extension (e.g. '.py').
        total_lines: Total lines in the file.
        blank_lines: Number of empty or whitespace-only lines.
        comment_lines: Number of lines recognized as comments.
        code_lines: Number of actual code lines (total - blank - comment).
    """

    file_path: str
    extension: str
    total_lines: int
    blank_lines: int
    comment_lines: int
    code_lines: int


class LOCError(Exception):
    """Base exception for the LOC counter module."""


class FileReadError(LOCError):
    """Raised when a file cannot be read due to permission or system error."""


class GitExecutionError(LOCError):
    """Raised when the git subprocess fails or is not available."""


class GitIgnoreMatcher:
    """Parses and matches file paths against .gitignore rules.

    This acts as a fallback when git is not available on the host system.
    """

    def __init__(self, root_dir: Path) -> None:
        """Initializes the matcher with ignore patterns from the workspace.

        Args:
            root_dir: The root directory of the workspace.
        """
        self.root_dir = root_dir.resolve()
        self.patterns: List[Tuple[Path, str]] = []
        self._load_gitignore_files()

    def _load_gitignore_files(self) -> None:
        """Recursively finds and parses .gitignore files in the workspace."""
        for path in self.root_dir.glob("**/.gitignore"):
            # Skip gitignores in virtual environment or build folders
            if any(part in path.parts for part in ("venv", "node_modules", ".git")):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        self.patterns.append((path.parent.resolve(), line))
            except Exception as e:
                logger.warning("Failed to read gitignore file %s: %s", path, e)

    def is_ignored(self, file_path: Path) -> bool:
        """Determines if a given file path matches any loaded ignore pattern.

        Args:
            file_path: The absolute or relative path to check.

        Returns:
            True if the path should be ignored, False otherwise.
        """
        abs_path = file_path.resolve()
        try:
            rel_parts = abs_path.relative_to(self.root_dir).parts
        except ValueError:
            # File is not under root_dir
            return True

        # Check explicit directories to ignore
        for part in rel_parts:
            if part in (".git", "node_modules", "venv", "__pycache__", ".pytest_cache", ".claude"):
                return True

        # Check patterns loaded from gitignores
        for base_dir, pattern in self.patterns:
            try:
                # If path is not under the directory containing the .gitignore, skip
                rel_to_base = abs_path.relative_to(base_dir)
            except ValueError:
                continue

            # Standardize pattern for comparison
            p_str = str(rel_to_base)
            if pattern.endswith("/"):
                # Directory pattern matching
                if fnmatch.fnmatch(p_str, pattern[:-1]) or fnmatch.fnmatch(p_str + "/", pattern):
                    return True
            else:
                # File pattern matching
                if fnmatch.fnmatch(p_str, pattern) or fnmatch.fnmatch(abs_path.name, pattern):
                    return True

        return False


def parse_lines_stateful(lines_generator: Generator[str, None, None], style: str) -> Tuple[int, int, int]:
    """Parses lines of a file to count total, blank, and comment lines.

    Handles single-line and multi-line comments depending on the language style.

    Args:
        lines_generator: Generator yielding lines of text from a file.
        style: Comment style identifier (e.g. 'hash', 'slash', 'css', 'html', 'sql', 'none').

    Returns:
        A tuple of (total_lines, blank_lines, comment_lines).
    """
    total = 0
    blank = 0
    comments = 0

    # Stateful variables for multiline comment parsing
    in_multiline = False

    for line in lines_generator:
        total += 1
        stripped = line.strip()

        if not stripped:
            blank += 1
            continue

        if style == "none":
            continue

        if style == "hash":
            if stripped.startswith("#"):
                comments += 1
            continue

        if style == "sql":
            if stripped.startswith("--"):
                comments += 1
            continue

        if style == "css":
            # Handles /* ... */
            if in_multiline:
                comments += 1
                if "*/" in stripped:
                    in_multiline = False
            else:
                if stripped.startswith("/*"):
                    comments += 1
                    if "*/" not in stripped:
                        in_multiline = True
            continue

        if style == "slash":
            # Handles // and /* ... */
            if in_multiline:
                comments += 1
                if "*/" in stripped:
                    in_multiline = False
            else:
                if stripped.startswith("//"):
                    comments += 1
                elif stripped.startswith("/*"):
                    comments += 1
                    if "*/" not in stripped:
                        in_multiline = True
            continue

        if style == "html":
            # Handles <!-- ... -->
            if in_multiline:
                comments += 1
                if "-->" in stripped:
                    in_multiline = False
            else:
                if stripped.startswith("<!--"):
                    comments += 1
                    if "-->" not in stripped:
                        in_multiline = True
            continue

    return total, blank, comments


def analyze_file(file_path: Path) -> Optional[FileStats]:
    """Analyzes a file to count lines.

    Args:
        file_path: Path to the target file.

    Returns:
        FileStats object if successful, None if skipped (e.g., binary or too large).

    Raises:
        FileReadError: If file exists but reading fails unexpectedly.
    """
    if not file_path.is_file():
        return None

    try:
        stat = file_path.stat()
        if stat.st_size > MAX_FILE_SIZE_BYTES:
            logger.debug("Skipping %s: file size exceeds limit", file_path)
            return None
    except OSError as e:
        raise FileReadError(f"Failed to get file stats for {file_path}: {e}") from e

    ext = file_path.suffix.lower()
    if ext not in COMMENT_STYLES:
        return None

    style = COMMENT_STYLES[ext]

    # Attempt to read file using UTF-8, fallback to latin-1 for safety
    encodings = ["utf-8", "latin-1"]
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                # Read using a generator to avoid loading entire files
                def line_gen() -> Generator[str, None, None]:
                    for line in f:
                        yield line

                total, blank, comments = parse_lines_stateful(line_gen(), style)
                code = total - blank - comments
                return FileStats(
                    file_path=str(file_path),
                    extension=ext,
                    total_lines=total,
                    blank_lines=blank,
                    comment_lines=comments,
                    code_lines=code,
                )
        except UnicodeDecodeError:
            continue
        except OSError as e:
            raise FileReadError(f"Error reading file {file_path}: {e}") from e

    logger.debug("Skipping binary/non-text file: %s", file_path)
    return None


def discover_files_via_git(root_dir: Path) -> List[Path]:
    """Discovers tracked and untracked files in the repository using Git.

    Args:
        root_dir: Root directory of the repository.

    Returns:
        List of Path objects representing files in the repo.

    Raises:
        GitExecutionError: If Git command fails or Git is not installed.
    """
    cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    try:
        result = subprocess.run(
            cmd,
            cwd=root_dir,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GitExecutionError("Git executable not found in PATH") from e

    if result.returncode != 0:
        raise GitExecutionError(f"Git command failed: {result.stderr.strip()}")

    discovered: List[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            discovered.append(root_dir / line)
    return discovered


def discover_files_manually(root_dir: Path) -> List[Path]:
    """Manually traverses directories using os.walk as a fallback.

    Applies gitignore rules using GitIgnoreMatcher.

    Args:
        root_dir: Root directory to scan.

    Returns:
        List of Path objects matching non-ignored files.
    """
    logger.info("Falling back to manual filesystem traversal...")
    matcher = GitIgnoreMatcher(root_dir)
    discovered: List[Path] = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # In-place modification of dirnames to prevent traversing ignored dirs
        dirnames[:] = [
            d
            for d in dirnames
            if not matcher.is_ignored(Path(dirpath) / d)
        ]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            if not matcher.is_ignored(fpath):
                discovered.append(fpath)

    return discovered


def aggregate_stats(stats_list: List[FileStats]) -> Dict[str, Dict[str, int]]:
    """Aggregates list of FileStats into a summary dictionary.

    Args:
        stats_list: List of individual FileStats.

    Returns:
        Dictionary mapping file extensions to aggregated counts.
    """
    aggregated: Dict[str, Dict[str, int]] = {}
    for stat in stats_list:
        ext = stat.extension
        if ext not in aggregated:
            aggregated[ext] = {
                "files": 0,
                "total": 0,
                "code": 0,
                "blank": 0,
                "comment": 0,
            }
        aggregated[ext]["files"] += 1
        aggregated[ext]["total"] += stat.total_lines
        aggregated[ext]["code"] += stat.code_lines
        aggregated[ext]["blank"] += stat.blank_lines
        aggregated[ext]["comment"] += stat.comment_lines
    return aggregated


def print_table(title: str, aggregated: Dict[str, Dict[str, int]]) -> None:
    """Prints a beautiful summary table of lines of code.

    Args:
        title: Title of the table section.
        aggregated: Aggregated statistics by extension.
    """
    if not aggregated:
        print(f"\n=== {title} ===")
        print("No source files found.")
        return

    print(f"\n=== {title} ===")
    header = f"{'Extension':<12} | {'Files':>6} | {'Code':>8} | {'Comments':>8} | {'Blank':>8} | {'Total':>10}"
    print(header)
    print("-" * len(header))

    total_files = 0
    total_code = 0
    total_comments = 0
    total_blank = 0
    total_lines = 0

    for ext, stats in sorted(aggregated.items(), key=lambda x: x[1]["code"], reverse=True):
        print(
            f"{ext:<12} | {stats['files']:>6,d} | {stats['code']:>8,d} | "
            f"{stats['comment']:>8,d} | {stats['blank']:>8,d} | {stats['total']:>10,d}"
        )
        total_files += stats["files"]
        total_code += stats["code"]
        total_comments += stats["comment"]
        total_blank += stats["blank"]
        total_lines += stats["total"]

    print("-" * len(header))
    print(
        f"{'TOTAL':<12} | {total_files:>6,d} | {total_code:>8,d} | "
        f"{total_comments:>8,d} | {total_blank:>8,d} | {total_lines:>10,d}"
    )


def main() -> int:
    """CLI execution entrypoint.

    Returns:
        0 on success, non-zero on failure.
    """
    parser = argparse.ArgumentParser(
        description="Count frontend and backend lines of code in this project, ignoring files in .gitignore."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format instead of terminal tables",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed diagnostic logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Resolve project root (assumed to be parent of scripts/ directory or current working directory)
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    if not (project_root / ".gitignore").exists():
        logger.warning(
            "Could not find .gitignore in project root %s. Relying on default ignores.",
            project_root,
        )

    # Discover files
    try:
        files = discover_files_via_git(project_root)
    except GitExecutionError as e:
        logger.warning("Git file discovery failed: %s", e)
        files = discover_files_manually(project_root)

    backend_stats: List[FileStats] = []
    frontend_stats: List[FileStats] = []

    # Separate and analyze files
    for filepath in files:
        # Check if file is under apps/api (Backend) or apps/web (Frontend)
        # We also support standalone-parser-viewer/backend and standalone-parser-viewer/frontend
        try:
            rel_path = filepath.relative_to(project_root)
        except ValueError:
            continue

        parts = rel_path.parts
        is_backend = False
        is_frontend = False

        if len(parts) >= 2 and parts[0] == "apps":
            if parts[1] == "api":
                is_backend = True
            elif parts[1] == "web":
                is_frontend = True
        elif len(parts) >= 2 and parts[0] == "standalone-parser-viewer":
            if parts[1] == "backend":
                is_backend = True
            elif parts[1] == "frontend":
                is_frontend = True

        if not (is_backend or is_frontend):
            continue

        try:
            stats = analyze_file(filepath)
            if stats:
                if is_backend:
                    backend_stats.append(stats)
                elif is_frontend:
                    frontend_stats.append(stats)
        except FileReadError as e:
            logger.error("Error parsing %s: %s", filepath, e)
            return 1

    backend_agg = aggregate_stats(backend_stats)
    frontend_agg = aggregate_stats(frontend_stats)

    if args.json:
        output_data = {
            "backend": backend_agg,
            "frontend": frontend_agg,
        }
        print(json.dumps(output_data, indent=2))
    else:
        print_table("BACKEND CODEBASE", backend_agg)
        print_table("FRONTEND CODEBASE", frontend_agg)

    return 0


if __name__ == "__main__":
    sys.exit(main())
