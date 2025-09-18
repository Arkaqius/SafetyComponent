#!/usr/bin/env python3
"""
Simple local deploy script.
Copies files from source directory to destination directory.

Features:
- Skips default junk: __pycache__, .git, *.pyc
- Supports glob ignore patterns (like .gitignore-ish) via:
    --ignore PATTERN           (can be repeated)
    --ignore-from FILE         (read patterns from a file; '#' comments allowed)
  Patterns are matched against POSIX-style relative paths (e.g., "tests/**", "**/tests/**", "*.md").
  A trailing "/" in a pattern means "this directory and everything under it" (auto-expanded to **).

- Optional --delete: remove files/dirs in destination that do not exist in source
  NOTE: ignored paths are *not deleted* (they are excluded from deletion checks).

Usage:
  python local_copy.py <src> <dst> [--delete] [--dry-run] [--ignore PAT]... [--ignore-from FILE]
"""

import argparse
import fnmatch
import os
import shutil
from pathlib import Path
from typing import List, Set

DEFAULT_EXCLUDED_DIRS = {"__pycache__", ".git"}
DEFAULT_EXCLUDED_FILE_SUFFIXES = {".pyc"}


def _load_patterns(ignore: List[str], ignore_from: List[Path]) -> List[str]:
    pats: List[str] = []
    # CLI patterns first
    for p in ignore:
        p = p.strip()
        if not p:
            continue
        pats.append(p)
    # file-based patterns
    for f in ignore_from:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip().replace("\\", "/")
                    if not s or s.startswith("#"):
                        continue
                    pats.append(s)
        except FileNotFoundError:
            print(f"WARN: ignore file not found: {f}")
    # Normalize: if pattern ends with '/', make it apply to the whole dir
    norm: List[str] = []
    for p in pats:
        p = p.replace("\\", "/")
        if p.endswith("/"):
            p = p + "**"
        norm.append(p)
    return norm


def _is_ignored(rel_posix: str, patterns: List[str]) -> bool:
    # rel_posix like "pkg/tests/test_foo.py"
    for pat in patterns:
        if fnmatch.fnmatch(rel_posix, pat):
            return True
    return False


def _collect_source_manifest(src: Path, patterns: List[str]) -> Set[str]:
    """
    Walk source and return set of relative POSIX file paths that should be copied.
    Applies default exclusions and ignore patterns.
    """
    out: Set[str] = set()
    for root, dirs, files in os.walk(src):
        # remove default excluded dirs
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDED_DIRS]

        # remove dirs matching ignore patterns
        pruned_dirs = []
        for d in dirs:
            rel_dir = (Path(root).relative_to(src) / d).as_posix()
            # match directory path; allow pattern that targets dir names or paths
            if _is_ignored(rel_dir + "/", patterns) or _is_ignored(rel_dir, patterns):
                # skip this whole subtree
                continue
            pruned_dirs.append(d)
        dirs[:] = pruned_dirs

        rel_root = Path(root).relative_to(src)
        for fname in files:
            if any(fname.endswith(suf) for suf in DEFAULT_EXCLUDED_FILE_SUFFIXES):
                continue
            rel_file = (rel_root / fname).as_posix()

            # Apply ignore patterns to the *file path*
            if _is_ignored(rel_file, patterns):
                continue

            out.add(rel_file)
    return out


def copy_tree(
    src: Path, dst: Path, delete: bool, dry_run: bool, patterns: List[str]
) -> None:
    src = src.resolve()
    dst = dst.resolve()

    if not src.is_dir():
        raise ValueError(f"Source path {src} is not a directory")

    print(f"Copying from {src} -> {dst}")
    # Build manifest of files to copy (relative POSIX paths)
    manifest = _collect_source_manifest(src, patterns)

    # Copy phase
    for rel in sorted(manifest):
        src_file = src / rel
        dst_file = dst / rel
        if dry_run:
            print(f"[DRY] COPY {src_file} -> {dst_file}")
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)

    # Delete phase
    if delete:
        # Walk destination and remove files not in manifest (and not ignored)
        for root, dirs, files in os.walk(dst, topdown=False):
            rel_root = Path(root).relative_to(dst)
            src_root = src / rel_root

            # Files
            for fname in files:
                dst_file = Path(root) / fname
                rel_file = (rel_root / fname).as_posix()

                # Skip deletion for ignored paths
                if _is_ignored(rel_file, patterns):
                    continue

                if rel_file not in manifest:
                    if dry_run:
                        print(f"[DRY] DELETE FILE {dst_file}")
                    else:
                        dst_file.unlink()

            # Dirs: remove empty dirs that no longer exist in source and are not ignored
            for d in dirs:
                dst_dir = Path(root) / d
                rel_dir = (rel_root / d).as_posix()
                if _is_ignored(rel_dir + "/", patterns) or _is_ignored(
                    rel_dir, patterns
                ):
                    continue
                src_dir = src / rel_dir
                # Remove if it doesn't exist in src or is empty after deletions
                try:
                    is_empty = not any(dst_dir.iterdir())
                except PermissionError:
                    is_empty = False
                if (not src_dir.exists() or is_empty) and is_empty:
                    if dry_run:
                        print(f"[DRY] RMDIR {dst_dir}")
                    else:
                        shutil.rmtree(dst_dir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description="Copy files locally from src to dst (with ignore patterns)"
    )
    ap.add_argument("src", help="Source directory")
    ap.add_argument("dst", help="Destination directory (e.g., Samba mount)")
    ap.add_argument(
        "--delete",
        action="store_true",
        help="Delete files not present in source (ignores are protected)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Only print actions")
    ap.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Glob ignore pattern (can be repeated). Example: '**/tests/**'",
    )
    ap.add_argument(
        "--ignore-from",
        action="append",
        default=[],
        help="File with ignore patterns, like a .gitignore",
    )
    args = ap.parse_args()

    patterns = _load_patterns(args.ignore, [Path(p) for p in args.ignore_from])

    copy_tree(
        Path(args.src),
        Path(args.dst),
        delete=args.delete,
        dry_run=args.dry_run,
        patterns=patterns,
    )


if __name__ == "__main__":
    main()
