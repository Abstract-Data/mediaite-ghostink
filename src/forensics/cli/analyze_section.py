"""Nested ``forensics analyze`` section diagnostics (section-profile / section-contrast)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._decorators import forensics_examples
from forensics.cli._envelope import status
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
from forensics.cli.analyze_models import resolve_analyze_subcommand_context
from forensics.cli.state import get_cli_state


def register_analyze_section_commands(app: typer.Typer) -> None:
    """Attach section subcommands to the parent ``analyze`` Typer app."""

    _SP_EPILOG, _sp_ex = forensics_examples("forensics analyze section-profile")

    @app.command(name="section-profile", epilog=_SP_EPILOG)
    @_sp_ex
    def section_profile_cmd(
        ctx: typer.Context,
        output: Annotated[
            Path | None,
            typer.Option(
                "--output",
                metavar="PATH",
                help=(
                    "Override the human-readable report path. JSON/CSV side artifacts "
                    "still land in data/analysis/."
                ),
            ),
        ] = None,
        features_dir: Annotated[
            Path | None,
            typer.Option(
                "--features-dir",
                metavar="PATH",
                help="Override the features parquet directory (default: data/features).",
            ),
        ] = None,
    ) -> None:
        """Phase 15 J3: newsroom-wide section descriptive report and J5 gate verdict."""
        from forensics.analysis.section_profile import GATE_OMNIBUS_ALPHA, run_section_profile

        ctx_paths = resolve_analyze_subcommand_context(features_dir=features_dir)

        result = run_section_profile(
            ctx_paths.settings,
            features_dir=ctx_paths.features_dir,
            analysis_dir=ctx_paths.analysis_dir,
            report_path=output,
        )
        fmt = get_cli_state(ctx).output_format
        status(f"section-profile: retained {len(result.sections)} sections", output_format=fmt)
        status(
            f"  significant families (p<{GATE_OMNIBUS_ALPHA}): "
            f"{len(result.significant_families)} "
            f"({', '.join(result.significant_families) or 'none'})",
            output_format=fmt,
        )
        status(
            f"  max off-diagonal cosine distance: {result.max_off_diagonal_distance:.4f}",
            output_format=fmt,
        )
        status(f"  J5 gate verdict: {result.gate_verdict}", output_format=fmt)
        if result.artifacts is not None:
            status(f"  report: {result.artifacts.report_md}", output_format=fmt)

    _SC_EPILOG, _sc_ex = forensics_examples(
        "forensics analyze section-contrast --author colby-hall",
    )

    @app.command(name="section-contrast", epilog=_SC_EPILOG)
    @_sc_ex
    def section_contrast_cmd(
        ctx: typer.Context,
        author: Annotated[
            str | None,
            typer.Option(
                "--author",
                metavar="SLUG",
                help=(
                    "Limit to one author slug. Default: every configured author "
                    "with a feature parquet under data/features/."
                ),
            ),
        ] = None,
        features_dir: Annotated[
            Path | None,
            typer.Option(
                "--features-dir",
                metavar="PATH",
                help="Override the features parquet directory (default: data/features).",
            ),
        ] = None,
    ) -> None:
        """Phase 15 J6: per-author section-contrast tests (Welch + MW + per-family BH)."""
        from forensics.analysis.section_contrast import compute_and_write_section_contrast
        from forensics.paths import load_feature_frame_for_author, resolve_author_rows
        from forensics.storage.repository import Repository

        ctx_paths = resolve_analyze_subcommand_context(features_dir=features_dir)

        with Repository(ctx_paths.db_path) as repo:
            author_rows = resolve_author_rows(repo, ctx_paths.settings, author_slug=author)

        fmt = get_cli_state(ctx).output_format
        if not author_rows:
            status(
                "section-contrast: no authors resolved (check --author / config.toml)",
                output_format=fmt,
            )
            raise fail(
                ctx,
                "analyze.section_contrast",
                "no_authors",
                "No authors resolved (check --author / config.toml).",
                exit_code=ExitCode.USAGE_ERROR,
            )

        written = 0
        for author_row in author_rows:
            df = load_feature_frame_for_author(
                ctx_paths.features_dir, author_row.slug, author_row.id
            )
            if df is None or df.is_empty():
                status(
                    f"section-contrast: skipped {author_row.slug} (no feature rows)",
                    output_format=fmt,
                )
                continue
            result, path = compute_and_write_section_contrast(
                df,
                author_id=author_row.id,
                author_slug=author_row.slug,
                analysis_dir=ctx_paths.analysis_dir,
                alpha=ctx_paths.settings.analysis.hypothesis.significance_threshold,
                bh_method=ctx_paths.settings.analysis.hypothesis.multiple_comparison_method,
            )
            written += 1
            if result.disposition == "insufficient_section_volume":
                status(
                    f"section-contrast: {author_row.slug} → insufficient_section_volume → {path}",
                    output_format=fmt,
                )
            else:
                status(
                    f"section-contrast: {author_row.slug} → {len(result.pairs)} pair(s) → {path}",
                    output_format=fmt,
                )
        status(f"section-contrast: wrote {written} artifact(s)", output_format=fmt)
