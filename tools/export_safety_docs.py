"""Export the safety baseline and bundle its linked repository references."""

import argparse
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REFERENCE_SUFFIXES = {".md", ".py", ".ts", ".yaml", ".yml"}


class ReferenceLinks(HTMLParser):
    """Collect local repository file links from a rendered document."""

    def __init__(self) -> None:
        super().__init__()
        self.paths: set[str] = set()

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> None:
        href = dict(attrs).get("href")
        if tag != "a" or not href:
            return
        address = urlsplit(href)
        path = unquote(address.path)
        if not address.scheme and not address.netloc and Path(path).suffix in REFERENCE_SUFFIXES:
            self.paths.add(path)


def bundle_references(output: Path, sources: list[Path]) -> int:
    """Copy tracked references to the paths used in the standalone export."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"], cwd=ROOT, check=True, capture_output=True,
    )
    tracked = set(result.stdout.decode("utf-8").split("\0"))
    html = output / "html"
    references: dict[Path, Path] = {}
    for document in sources:
        page = html / document.relative_to(DOCS).with_suffix(".sdoc.html")
        source_dir = DOCS / page.parent.relative_to(html)
        links = ReferenceLinks()
        links.feed(page.read_text(encoding="utf-8"))
        for path in links.paths:
            source = (source_dir / path).resolve()
            target = (page.parent / path).resolve()
            if not source.is_relative_to(ROOT) or not target.is_relative_to(output):
                raise ValueError(f"{page.name} has an out-of-scope link: {path}")
            if source.relative_to(ROOT).as_posix() not in tracked or not source.is_file():
                raise ValueError(f"{page.name} links to a missing or untracked file: {path}")
            references[target] = source
    for target, source in references.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return len(references)


def main() -> None:
    """Export the system and feature architecture sources as HTML and JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/strictdoc")
    output = parser.parse_args().output_dir.resolve()
    if ROOT.is_relative_to(output):
        parser.error("--output-dir must be separate from the repository root")
    sources = sorted((DOCS / "sys").glob("*.sdoc"))
    sources.extend(sorted((DOCS / "features").glob("* - Architecture.sdoc")))
    subprocess.run(
        [
            sys.executable, "-c", "from strictdoc.cli.main import main; raise SystemExit(main())",
            "export", "--config", str(DOCS / "strictdoc_config.py"),
            "--formats=html,json", "--output-dir", str(output), "--no-parallelization",
            *(str(source) for source in sources),
        ],
        cwd=ROOT, check=True,
    )
    count = bundle_references(output, sources)
    print(f"Bundled {count} repository references. Open {output / 'html/index.html'}")


if __name__ == "__main__":
    main()
