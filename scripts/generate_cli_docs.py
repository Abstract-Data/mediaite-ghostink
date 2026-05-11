#!/usr/bin/env python3
"""Generate Starlight-friendly Markdown reference docs for the forensics CLI.

Walks the Typer ``forensics.cli:app`` command tree and emits one Markdown file
per command into ``--out`` (default: ``website/src/content/docs/cli``).

The generated tree is idempotent: re-running on a clean tree produces no diffs.

Run via:
    uv run python scripts/generate_cli_docs.py
    uv run python scripts/generate_cli_docs.py --out website/src/content/docs/cli

Versioned mode (Option C: per-release CLI reference). When the orchestrator
(``website/scripts/build-cli-docs.mjs``) shells out for a specific tag, it
passes:

    --out         website/src/content/docs/cli/<safeTag>       (subdir per tag)
    --version     v0.3.0                                       (the git tag)
    --version-label "0.3.0"                                    (display label)
    --version-default                                          (only on latest)

In versioned mode the script:

  * Writes ``version: "<tag>"`` and (when set) ``versionLabel:`` /
    ``versionDefault: true`` into every page's YAML frontmatter. This is what
    ``@abstractdata/starlight-theme``'s ``<VersionPicker>`` auto-discovers.
  * Rewrites cross-page links (subcommand tables, ``cli/index.md``) so they
    target the same version subdirectory, e.g. ``/mediaite-ghostink/cli/0-1-2/forensics-analyze/``.
  * Tags every page's ``editUrl`` at the version tag rather than ``main``,
    so "Edit this page" sends reviewers to the released code, not HEAD.

In unversioned mode (no ``--version`` flag) behavior is unchanged: same slugs,
same links, no version frontmatter — preserves the latest-only-at-root URL.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import click
from typer.main import get_command

from forensics.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "website" / "src" / "content" / "docs" / "cli"
EDIT_BASE_TEMPLATE = "https://github.com/Abstract-Data/mediaite-ghostink/edit/{ref}"

SITE_BASE = "/mediaite-ghostink"


def safe_tag(tag: str) -> str:
    """Mirror the ``safeTag`` in build-python-docs.mjs / VersionPicker.

    Astro normalises URL segments by stripping dots, so a tag like ``v0.1.0``
    must become ``0-1-0`` *before* it ever appears in a path. Otherwise the
    on-disk directory and the rendered URL diverge and the VersionPicker's
    dropdown navigation 404s.
    """
    stripped = tag.lstrip("v")
    return re.sub(r"[^a-zA-Z0-9_-]", "-", stripped)


def slugify(name: str) -> str:
    """Lowercase, dash-separated, filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "command"


def escape_yaml(s: str) -> str:
    return s.replace('"', '\\"')


def truncate(s: str, n: int = 160) -> str:
    s = " ".join(s.split())
    if len(s) <= n:
        return s
    cut = s[:n].rstrip()
    last_space = cut.rfind(" ")
    if last_space > n - 30:
        return f"{cut[:last_space]}…"
    return f"{cut}…"


def cli_link(slug: str, *, version_segment: str) -> str:
    """Absolute, base-prefixed Starlight URL for a CLI page slug.

    ``version_segment`` is the empty string in unversioned mode and
    ``<safe-tag>/`` (with trailing slash) in versioned mode, so callers can
    interpolate it without conditional branching.
    """
    return f"{SITE_BASE}/cli/{version_segment}{slug}/"


def render_options(cmd: click.Command, ctx: click.Context) -> list[str]:
    rows: list[tuple[str, str]] = []
    for param in cmd.get_params(ctx):
        record = param.get_help_record(ctx)
        if record is None:
            continue
        opts, desc = record
        clean_opts = opts.replace("|", "\\|").strip()
        clean_desc = (desc or "").replace("|", "\\|").replace("\n", " ").strip()
        rows.append((clean_opts, clean_desc))
    if not rows:
        return []
    lines = ["## Options", "", "| Option | Description |", "|--------|-------------|"]
    lines.extend(f"| `{opts}` | {desc} |" for opts, desc in rows)
    lines.append("")
    return lines


def render_subcommands(
    cmd: click.Group,
    ctx: click.Context,
    parent_slug: str,
    *,
    version_segment: str,
) -> list[str]:
    names = sorted(cmd.list_commands(ctx))
    if not names:
        return []
    lines = ["## Subcommands", "", "| Command | Description |", "|---------|-------------|"]
    for name in names:
        sub = cmd.get_command(ctx, name)
        if sub is None:
            continue
        short = (sub.short_help or sub.help or "").split("\n", 1)[0].strip().replace("|", "\\|")
        child_slug = slugify(f"{parent_slug}-{name}") if parent_slug else slugify(name)
        lines.append(
            f"| [`{name}`]({cli_link(child_slug, version_segment=version_segment)}) | {short} |"
        )
    lines.append("")
    return lines


def render_page(
    *,
    full_name: str,
    slug: str,
    cmd: click.Command,
    parent_path: list[str],
    repo_rel_source: str | None,
    version_tag: str | None,
    version_label: str | None,
    version_default: bool,
    edit_ref: str,
    version_segment: str,
) -> str:
    info_name = parent_path[-1] if parent_path else "forensics"
    ctx = click.Context(cmd, info_name=info_name, parent=None)

    short = (cmd.short_help or "").strip()
    help_text = (cmd.help or "").strip()

    description_source = short or help_text.split("\n\n", 1)[0]
    description = truncate(description_source.replace('"', "'"), 160) if description_source else ""

    fm = ["---", f'title: "{escape_yaml(full_name)}"']
    if description:
        fm.append(f'description: "{escape_yaml(description)}"')
    if repo_rel_source:
        fm.append(f'editUrl: "{EDIT_BASE_TEMPLATE.format(ref=edit_ref)}/{repo_rel_source}"')
    # Version frontmatter (auto-discovered by @abstractdata/starlight-theme's
    # <VersionPicker>). Omitted entirely on un-versioned builds so existing
    # un-versioned pages don't pick up an inappropriate "default" tag.
    if version_tag:
        fm.append(f'version: "{escape_yaml(version_tag)}"')
        if version_label:
            fm.append(f'versionLabel: "{escape_yaml(version_label)}"')
        if version_default:
            fm.append("versionDefault: true")
        # Pages under a version subdir are hidden from the sidebar — they're
        # reachable via the VersionPicker dropdown only. The default version
        # is also aliased at the un-versioned URL (which IS sidebar-visible),
        # so this `hidden: true` only fires for non-aliased builds (anything
        # with a non-empty version_segment). Without this, the sidebar would
        # show every command N+1 times (once for each version + the alias).
        if version_segment:
            fm.extend(["sidebar:", "  hidden: true"])
    fm.extend(["---", ""])

    lines = list(fm)
    if help_text:
        lines.extend([help_text, ""])

    usage = cmd.get_usage(ctx).strip()
    if usage:
        usage_pretty = usage.replace("Usage:", "").strip()
        usage_pretty = re.sub(rf"^{re.escape(info_name)}\b", full_name, usage_pretty)
        lines.extend(["## Usage", "", "```bash", usage_pretty, "```", ""])

    lines.extend(render_options(cmd, ctx))

    if isinstance(cmd, click.Group):
        lines.extend(render_subcommands(cmd, ctx, slug, version_segment=version_segment))

    body = "\n".join(lines).rstrip() + "\n"
    return body


def walk(
    cmd: click.Command,
    parent_path: list[str],
    out_dir: Path,
    index_rows: list[tuple[str, str, str]],
    *,
    version_tag: str | None,
    version_label: str | None,
    version_default: bool,
    edit_ref: str,
    version_segment: str,
) -> None:
    """Recursively render ``cmd`` and its subcommands.

    ``parent_path`` always starts with the root command name (``forensics``)
    so the rendered slug, the parent's subcommand-table link, and the on-disk
    filename agree.
    """
    name = parent_path[-1]
    full_name = " ".join(parent_path)
    slug = slugify(full_name)
    out_path = out_dir / f"{slug}.md"

    page = render_page(
        full_name=full_name,
        slug=slug,
        cmd=cmd,
        parent_path=parent_path,
        repo_rel_source="src/forensics/cli/__init__.py",
        version_tag=version_tag,
        version_label=version_label,
        version_default=version_default,
        edit_ref=edit_ref,
        version_segment=version_segment,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page)

    short = (cmd.short_help or "").strip()
    help_first = (cmd.help or "").split("\n", 1)[0].strip()
    summary = truncate(short or help_first, 160)
    index_rows.append((full_name, slug, summary))

    if isinstance(cmd, click.Group):
        ctx = click.Context(cmd, info_name=name, parent=None)
        for sub_name in sorted(cmd.list_commands(ctx)):
            sub = cmd.get_command(ctx, sub_name)
            if sub is None:
                continue
            walk(
                sub,
                [*parent_path, sub_name],
                out_dir,
                index_rows,
                version_tag=version_tag,
                version_label=version_label,
                version_default=version_default,
                edit_ref=edit_ref,
                version_segment=version_segment,
            )


def write_index(
    out_dir: Path,
    rows: list[tuple[str, str, str]],
    *,
    version_tag: str | None,
    version_label: str | None,
    version_default: bool,
    edit_ref: str,
    version_segment: str,
) -> None:
    cli_entry_url = f"https://github.com/Abstract-Data/mediaite-ghostink/blob/{edit_ref}/src/forensics/cli/__init__.py"
    suffix = f" — version `{version_label or version_tag}`" if version_tag else ""
    lead = (
        f"The `forensics` console script is a Typer app entered at "
        f"[`src/forensics/cli/__init__.py`]({cli_entry_url}){suffix}. "
        "Every command and subcommand below has its own page with usage, "
        "options, and subcommands (when present)."
    )
    fm = [
        "---",
        'title: "CLI reference"',
        'description: "Auto-generated reference for every forensics CLI command and subcommand."',
    ]
    if version_tag:
        fm.append(f'version: "{escape_yaml(version_tag)}"')
        if version_label:
            fm.append(f'versionLabel: "{escape_yaml(version_label)}"')
        if version_default:
            fm.append("versionDefault: true")
        if version_segment:
            fm.extend(["sidebar:", "  hidden: true"])
    fm.extend(["---", ""])

    lines = list(fm)
    lines.extend(
        [
            lead,
            "",
            "| Command | Description |",
            "|---------|-------------|",
        ]
    )
    for full_name, slug, summary in rows:
        clean_summary = summary.replace("|", "\\|")
        href = cli_link(slug, version_segment=version_segment)
        lines.append(f"| [`{full_name}`]({href}) | {clean_summary} |")
    lines.append("")
    (out_dir / "index.md").write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=True,
        help="Remove the output directory before writing (default: on).",
    )
    parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="Keep existing files in the output directory.",
    )
    parser.add_argument(
        "--version",
        dest="version_tag",
        default=None,
        help=(
            "Git tag for this build (writes `version:` frontmatter for "
            "VersionPicker auto-discovery)."
        ),
    )
    parser.add_argument(
        "--version-label",
        default=None,
        help=(
            "Human label for the version (e.g. '0.1.2' or '0.3 (legacy)'). "
            "Defaults to the tag with leading 'v' stripped."
        ),
    )
    parser.add_argument(
        "--version-default",
        action="store_true",
        help="Mark this version as the default (writes `versionDefault: true`).",
    )
    parser.add_argument(
        "--version-segment",
        default=None,
        help=(
            "URL segment for cross-page links (default: derived from --version "
            "via safeTag; pass empty string to alias a default version at the "
            "un-versioned URL)."
        ),
    )
    args = parser.parse_args(argv)

    version_tag: str | None = args.version_tag
    version_label: str | None = args.version_label
    if version_tag and version_label is None:
        version_label = version_tag.lstrip("v")
    if args.version_segment is not None:
        version_segment = args.version_segment.strip("/")
        version_segment = f"{version_segment}/" if version_segment else ""
    elif version_tag:
        version_segment = f"{safe_tag(version_tag)}/"
    else:
        version_segment = ""
    edit_ref = version_tag if version_tag else "main"

    out_dir: Path = args.out
    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    click_root = get_command(app)
    index_rows: list[tuple[str, str, str]] = []
    walk(
        click_root,
        ["forensics"],
        out_dir,
        index_rows,
        version_tag=version_tag,
        version_label=version_label,
        version_default=args.version_default,
        edit_ref=edit_ref,
        version_segment=version_segment,
    )
    write_index(
        out_dir,
        index_rows,
        version_tag=version_tag,
        version_label=version_label,
        version_default=args.version_default,
        edit_ref=edit_ref,
        version_segment=version_segment,
    )

    where = (
        out_dir.relative_to(REPO_ROOT)
        if out_dir.is_absolute() and REPO_ROOT in out_dir.parents
        else out_dir
    )
    tag_note = f" [version={version_tag}]" if version_tag else ""
    sys.stderr.write(f"generate_cli_docs: wrote {len(index_rows)} page(s) to {where}{tag_note}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
