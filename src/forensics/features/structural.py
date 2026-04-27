"""Structural feature extractors."""

from __future__ import annotations

import math
import re
from statistics import median
from typing import Any

from scipy.stats import skew
from spacy.tokens import Doc

from forensics.features.pos_patterns import max_dep_depth_sentence


def _sentence_word_counts(doc: Doc) -> list[int]:
    counts: list[int] = []
    for sent in doc.sents:
        n = sum(1 for t in sent if t.is_alpha)
        counts.append(n)
    return counts or [0]


def _paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n+", text.strip())
    return [p.strip() for p in parts if p.strip()] or [text.strip() or ""]


def _passive_sentence(sent: Any) -> bool:
    for t in sent:
        if t.dep_ in ("nsubjpass", "auxpass"):
            return True
    return False


def extract_structural_features(text: str, doc: Doc) -> dict[str, Any]:
    """Sentence, paragraph, punctuation, and passive-voice structure."""
    sent_counts = _sentence_word_counts(doc)
    n_sents = len(sent_counts)
    mean_sc = sum(sent_counts) / n_sents if n_sents else float("nan")
    med_sc = float(median(sent_counts)) if sent_counts else float("nan")
    std_sc = (
        math.sqrt(sum((x - mean_sc) ** 2 for x in sent_counts) / n_sents) if n_sents > 1 else 0.0
    )
    sk = float(skew(sent_counts)) if n_sents >= 3 else 0.0

    depths = [max_dep_depth_sentence(s) for s in doc.sents]
    sub_depth = sum(depths) / len(depths) if depths else float("nan")

    n_tokens = sum(1 for t in doc if not t.is_space)
    conj = sum(1 for t in doc if t.pos_ in ("CCONJ", "SCONJ"))
    conj_freq = conj / n_tokens if n_tokens else float("nan")

    sents_list = list(doc.sents)
    passive_n = sum(1 for s in sents_list if _passive_sentence(s))
    passive_ratio = passive_n / len(sents_list) if sents_list else float("nan")

    paras = _paragraphs(text)
    sent_per_para: list[int] = []
    para_word_counts: list[int] = []
    for p in paras:
        raw_sents = re.split(r"(?<=[.!?])\s+", p)
        raw_sents = [s for s in raw_sents if s.strip()]
        sent_per_para.append(len(raw_sents) if raw_sents else 1)
        para_word_counts.append(len(re.findall(r"\b\w+\b", p)))

    spp = sum(sent_per_para) / len(sent_per_para) if sent_per_para else float("nan")
    if len(para_word_counts) > 1:
        m = sum(para_word_counts) / len(para_word_counts)
        pvar = math.sqrt(sum((w - m) ** 2 for w in para_word_counts) / len(para_word_counts))
    else:
        pvar = 0.0

    chars = len(text) or 1
    punct_keys = (";", "—", "!", "(", ")", ":", "...", '"')
    profile: dict[str, float] = {}
    for ch in punct_keys:
        if ch == "...":
            count = text.count("...")
        elif ch == "—":
            count = text.count("—") + text.count("–")
        else:
            count = text.count(ch)
        profile[ch] = 1000.0 * count / chars

    return {
        "sent_length_mean": mean_sc,
        "sent_length_median": med_sc,
        "sent_length_std": std_sc,
        "sent_length_skewness": sk,
        "subordinate_clause_depth": sub_depth,
        "conjunction_freq": conj_freq,
        "passive_voice_ratio": passive_ratio,
        "sentences_per_paragraph": spp,
        "paragraph_length_variance": pvar,
        "punctuation_profile": profile,
    }
