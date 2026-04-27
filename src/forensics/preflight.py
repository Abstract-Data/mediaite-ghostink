"""Environment checks before pipeline runs.

:class:`PreflightReport` aggregates ``pass`` / ``warn`` / ``fail`` per check.
``fail`` blocks the pipeline (Python, spaCy, disk, config, placeholders); optional
tools (Quarto, Ollama, embedding cache) surface as ``warn`` unless ``strict``.
"""

from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

CheckStatus = Literal["pass", "warn", "fail"]

_MIN_PYTHON: tuple[int, int] = (3, 13)
_MIN_FREE_GB: float = 5.0
_PLACEHOLDER_SLUGS: frozenset[str] = frozenset({"placeholder-target", "placeholder-control"})


class _SettingsLike(Protocol):
    """Duck-typed settings (``authors``, ``analysis``, optional ``baseline``)."""

    authors: list  # noqa: UP006  - runtime duck-type only
    analysis: object
    baseline: object


@dataclass(frozen=True)
class PreflightCheck:
    """One named check outcome."""

    name: str
    status: CheckStatus
    message: str


@dataclass(frozen=True)
class PreflightReport:
    """All checks from :func:`run_all_preflight_checks`."""

    checks: tuple[PreflightCheck, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """No ``fail`` checks."""
        return not self.has_failures

    @property
    def has_failures(self) -> bool:
        return any(c.status == "fail" for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status == "warn" for c in self.checks)

    def failures(self) -> tuple[PreflightCheck, ...]:
        return tuple(c for c in self.checks if c.status == "fail")

    def warnings(self) -> tuple[PreflightCheck, ...]:
        return tuple(c for c in self.checks if c.status == "warn")


def check_python_version(minimum: tuple[int, int] = _MIN_PYTHON) -> PreflightCheck:
    """Fail when the interpreter is below ``minimum``."""
    current = sys.version_info[:2]
    detail = f"Python {current[0]}.{current[1]} (need >= {minimum[0]}.{minimum[1]})"
    if current >= minimum:
        return PreflightCheck("Python version", "pass", detail)
    return PreflightCheck("Python version", "fail", detail)


def check_spacy_model(model_name: str = "en_core_web_md") -> PreflightCheck:
    """Fail when ``model_name`` cannot be loaded."""
    try:
        import spacy
    except ImportError as exc:
        return PreflightCheck("spaCy model", "fail", f"spacy not importable: {exc}")
    try:
        nlp = spacy.load(model_name)
    except OSError as exc:
        hint = f"Run: uv run python -m spacy download {model_name}"
        return PreflightCheck("spaCy model", "fail", f"{exc} — {hint}")
    version = nlp.meta.get("version", "?")
    return PreflightCheck("spaCy model", "pass", f"{model_name} loaded ({version})")


def check_sentence_transformer(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> PreflightCheck:
    """Warn if the embedding model is not importable or not cached yet."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        return PreflightCheck(
            "Embedding model",
            "warn",
            f"sentence-transformers not importable: {exc}",
        )
    try:
        model = SentenceTransformer(model_name)
    except (OSError, RuntimeError, ValueError) as exc:
        return PreflightCheck(
            "Embedding model",
            "warn",
            f"Will auto-download on first use ({exc})",
        )
    dim = model.get_sentence_embedding_dimension()
    return PreflightCheck("Embedding model", "pass", f"{model_name} ({dim}-dim)")


def check_quarto() -> PreflightCheck:
    """Warn when ``quarto`` is not on ``PATH``."""
    binary = shutil.which("quarto")
    if binary:
        return PreflightCheck("Quarto", "pass", f"Found at {binary}")
    return PreflightCheck(
        "Quarto",
        "warn",
        "Not found — reports will not render. Install: brew install quarto",
    )


def check_ollama(settings: _SettingsLike) -> PreflightCheck:
    """Warn when baseline is configured but ``ollama`` is missing."""
    baseline = getattr(settings, "baseline", None)
    if baseline is None:
        return PreflightCheck("Ollama", "pass", "Baseline not configured, skipping")
    binary = shutil.which("ollama")
    if binary:
        return PreflightCheck("Ollama", "pass", f"Found at {binary}")
    return PreflightCheck(
        "Ollama",
        "warn",
        "Not found — AI baseline generation unavailable (optional)",
    )


def check_disk_space(data_dir: Path, minimum_gb: float = _MIN_FREE_GB) -> PreflightCheck:
    """Fail when free space under ``data_dir``'s filesystem is below ``minimum_gb``."""
    probe = data_dir if data_dir.exists() else data_dir.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError as exc:
        return PreflightCheck("Disk space", "fail", f"Could not stat {probe}: {exc}")
    free_gb = usage.free / (1024**3)
    detail = f"{free_gb:.1f} GB free at {probe} (need >= {minimum_gb:.0f} GB)"
    if free_gb >= minimum_gb:
        return PreflightCheck("Disk space", "pass", detail)
    return PreflightCheck("Disk space", "fail", detail)


def check_no_placeholder_authors(settings: _SettingsLike) -> PreflightCheck:
    """Fail when placeholder author slugs are still present."""
    authors = list(getattr(settings, "authors", []) or [])
    bad = [a for a in authors if getattr(a, "slug", "") in _PLACEHOLDER_SLUGS]
    if bad:
        return PreflightCheck(
            "Author config",
            "fail",
            "config.toml still has placeholder authors — run setup wizard or edit manually",
        )
    return PreflightCheck(
        "Author config",
        "pass",
        f"{len(authors)} author(s) configured",
    )


def check_config_parses() -> PreflightCheck:
    """Fail when settings cannot be loaded (missing/invalid TOML or validation)."""
    import tomllib

    import pydantic

    try:
        from forensics.config.settings import get_settings

        get_settings()
    except (FileNotFoundError, tomllib.TOMLDecodeError, pydantic.ValidationError) as exc:
        return PreflightCheck("Config file", "fail", f"config.toml did not parse: {exc}")
    return PreflightCheck("Config file", "pass", "config.toml parses successfully")


def run_all_preflight_checks(
    settings: _SettingsLike | None = None,
    *,
    strict: bool = False,
) -> PreflightReport:
    """Run all checks. With ``strict``, promote every ``warn`` to ``fail`` (CI lanes)."""
    from forensics.config import get_project_root

    resolved = settings
    config_check = check_config_parses()
    if resolved is None and config_check.status == "pass":
        try:
            from forensics.config.settings import get_settings

            resolved = get_settings()
        except Exception as exc:  # noqa: BLE001
            config_check = PreflightCheck(
                "Config file", "fail", f"config.toml did not parse: {exc}"
            )

    data_dir = get_project_root() / "data"

    spacy_model = getattr(resolved, "spacy_model", "en_core_web_md")
    checks: list[PreflightCheck] = [
        config_check,
        check_python_version(),
        check_spacy_model(spacy_model),
        check_disk_space(data_dir),
    ]

    if resolved is not None:
        embedding_model = getattr(
            getattr(resolved, "analysis", None),
            "embedding_model",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        checks.append(check_sentence_transformer(embedding_model))
        checks.append(check_ollama(resolved))
        checks.append(check_no_placeholder_authors(resolved))
    else:
        checks.append(check_sentence_transformer())
        checks.append(
            PreflightCheck(
                "Ollama",
                "warn",
                "Skipped — settings unavailable",
            )
        )
        checks.append(
            PreflightCheck(
                "Author config",
                "fail",
                "settings unavailable — cannot verify authors",
            )
        )

    checks.append(check_quarto())

    if strict:
        checks = [
            PreflightCheck(c.name, "fail", c.message) if c.status == "warn" else c for c in checks
        ]

    return PreflightReport(checks=tuple(checks))


__all__ = [
    "CheckStatus",
    "PreflightCheck",
    "PreflightReport",
    "check_config_parses",
    "check_disk_space",
    "check_no_placeholder_authors",
    "check_ollama",
    "check_python_version",
    "check_quarto",
    "check_sentence_transformer",
    "check_spacy_model",
    "run_all_preflight_checks",
]
