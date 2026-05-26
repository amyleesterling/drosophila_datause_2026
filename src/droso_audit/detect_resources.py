"""Resource / tool mention detection over extracted full text.

Pure-stdlib (regex) so it can be unit-tested without heavy deps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Map each detectable term to its canonical ``resource_detected_in_text`` label.
# Order matters only for reporting; matching is done per-term.
RESOURCE_TERMS: dict[str, str] = {
    # hemibrain / neuPrint
    r"hemibrain": "hemibrain",
    r"neu[\s\-]?print": "neuPrint",
    # FAFB
    r"fafb(?:[\s\-]?v?14)?": "FAFB",
    r"full adult fly brain": "FAFB",
    # FlyWire & platform tooling
    r"flywire": "FlyWire",
    r"fafb[\s\-]?flywire": "FlyWire",
    r"codex(?:\.flywire\.ai)?": "Codex",
    r"caveclient": "CAVE",
    r"\bcave\b": "CAVE",
    r"cloudvolume": "CAVE",
    r"catmaid": "CATMAID",
    # VNC connectomes
    r"\bmanc\b": "MANC",
    r"male adult nerve cord": "MANC",
    r"male.{0,20}ventral nerve cord": "MANC",
    r"malevnc": "malevnc",
    r"\bfanc\b": "FANC",
    r"female adult nerve cord": "FANC",
    # python libraries
    r"\bnavis\b": "navis",
    r"fafbseg": "fafbseg",
    r"nblast": "navis",
}

# Terms that, on their own, are weak signals (could be generic) but still
# recorded as evidence. Used by classify rules, not as a resource label.
WEAK_TERMS = [
    r"connectivity matrix",
    r"adjacency matrix",
    r"synaptic partners",
    r"upstream partners",
    r"downstream partners",
    r"root\s?id",
    r"segment\s?id",
    r"supervoxel",
    r"skeleton",
    r"\bmesh(?:es)?\b",
]

# Compile once.
_COMPILED = [(re.compile(pat, re.IGNORECASE), label) for pat, label in RESOURCE_TERMS.items()]
_WEAK_COMPILED = [re.compile(p, re.IGNORECASE) for p in WEAK_TERMS]

# Sentence splitter — deliberately simple; connectome papers use a lot of
# abbreviations, so we keep it conservative.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\d])")


@dataclass
class Mention:
    resource_term: str          # the canonical label (e.g. "FlyWire")
    matched_text: str           # the literal matched substring
    section: str
    sentence_window: str
    start_char: int
    end_char: int
    is_weak: bool = False


def split_sentences(text: str) -> list[tuple[int, str]]:
    """Return (start_offset, sentence) tuples for a block of text."""
    out: list[tuple[int, str]] = []
    pos = 0
    for chunk in _SENT_SPLIT.split(text):
        idx = text.find(chunk, pos)
        if idx < 0:
            idx = pos
        out.append((idx, chunk))
        pos = idx + len(chunk)
    return out


def _window_for(text: str, start: int, end: int, n: int = 2) -> str:
    """Return a window of ``n`` sentences before/after the match sentence."""
    sents = split_sentences(text)
    if not sents:
        return text[max(0, start - 200) : end + 200].strip()
    # Find sentence index containing the match start.
    hit = 0
    for i, (off, s) in enumerate(sents):
        if off <= start < off + len(s):
            hit = i
            break
    lo = max(0, hit - n)
    hi = min(len(sents), hit + n + 1)
    return " ".join(s for _, s in sents[lo:hi]).strip()


def detect_mentions(text: str, section: str = "unknown", include_weak: bool = True) -> list[Mention]:
    """Find all resource (and optionally weak) term mentions in ``text``."""
    if not text:
        return []
    mentions: list[Mention] = []
    seen: set[tuple[str, int]] = set()

    for rx, label in _COMPILED:
        for m in rx.finditer(text):
            key = (label, m.start())
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                Mention(
                    resource_term=label,
                    matched_text=m.group(0),
                    section=section,
                    sentence_window=_window_for(text, m.start(), m.end()),
                    start_char=m.start(),
                    end_char=m.end(),
                )
            )

    if include_weak:
        for rx in _WEAK_COMPILED:
            for m in rx.finditer(text):
                mentions.append(
                    Mention(
                        resource_term=m.group(0).lower(),
                        matched_text=m.group(0),
                        section=section,
                        sentence_window=_window_for(text, m.start(), m.end()),
                        start_char=m.start(),
                        end_char=m.end(),
                        is_weak=True,
                    )
                )
    return mentions


def detect_in_sections(sections: list[dict], include_weak: bool = True) -> list[Mention]:
    """Run detection across a list of ``{"section":..., "text":...}`` dicts."""
    all_mentions: list[Mention] = []
    for sec in sections:
        all_mentions.extend(
            detect_mentions(sec.get("text", ""), section=sec.get("section", "unknown"), include_weak=include_weak)
        )
    return all_mentions


def resources_detected(mentions: list[Mention]) -> str:
    """Semicolon-joined unique non-weak resource labels, or 'none_detected'."""
    labels = sorted({m.resource_term for m in mentions if not m.is_weak})
    return ";".join(labels) if labels else "none_detected"
