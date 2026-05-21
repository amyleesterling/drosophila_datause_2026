"""Classification: deterministic rules, optional LLM, and the merge logic.

The rule engine (``rule_preclassify``) and merge logic (``merge_classification``)
are pure functions with no network/LLM dependency, so they are unit-testable.
The LLM call lives in ``llm_classify`` and is only used when a key is present.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from .config import SETTINGS


# --------------------------------------------------------------------------- #
# Rule phrase banks
# --------------------------------------------------------------------------- #
STRONG_YES_PATTERNS = [
    r"we (?:used|use|queried|query|analy[sz]ed|extracted|downloaded|obtained|retrieved)\b[^.]{0,80}\b"
    r"(hemibrain|neu\s?print|flywire|fafb|manc|catmaid|cave|codex|connectome)",
    r"\b(?:using|from|within|via)\s+(?:the\s+)?(hemibrain|flywire|fafb|manc)\s+(?:connectome|dataset|data|volume)",
    r"connectome[- ](?:constrained|based|derived)\s+(?:model|network|simulation)",
    r"(?:identified|analy[sz]ed|examined|traced)\s+(?:the\s+)?(?:upstream|downstream)?\s*synaptic partners",
    r"(?:constructed|built|extracted|computed)\s+(?:a\s+)?(?:connectivity|adjacency)\s+matrix",
    r"(?:we|the authors)\s+(?:used|queried)\s+neu\s?print",
    r"from the (hemibrain|flywire|manc|fafb) (?:dataset|connectome|data)",
    r"(?:neuron|root|segment)\s?ids?\s+(?:were|from|of)\b",
    r"proofread(?:ing)?\b[^.]{0,60}\b(flywire|fafb|connectome|segmentation)",
]

# Phrases that, when they are the ONLY context, indicate background-only use.
BACKGROUND_PATTERNS = [
    r"recent connectomes? (?:have|has)\b",
    r"large[- ]scale connectomics has\b",
    r"connectomic resources such as\b",
    r"the hemibrain project demonstrated\b",
    r"flywire provides an example\b",
    r"such as (?:the )?(?:hemibrain|flywire)\b",
    r"connectomes? (?:such as|like|including)\b",
    r"advances in connectomics\b",
]

REVIEW_TITLE_HINTS = ["review", "perspective", "commentary", "opinion", "outlook", "primer", "news and views"]

_STRONG_YES = [re.compile(p, re.IGNORECASE) for p in STRONG_YES_PATTERNS]
_BACKGROUND = [re.compile(p, re.IGNORECASE) for p in BACKGROUND_PATTERNS]

# Sections where data-use evidence is meaningful.
DATA_USE_SECTIONS = {"methods", "results", "data_availability", "supplement", "figure_caption"}


@dataclass
class Classification:
    actually_uses_connectome_data: str = "unclear"
    use_category: str = "G_unclassifiable_no_full_text"
    use_subcategory: str = "unknown"
    resource_detected_in_text: str = "none_detected"
    evidence_quote: str = ""
    evidence_section: str = "unknown"
    evidence_location: str = ""
    confidence: str = "low"
    manual_review_needed: str = "yes"
    manual_review_reason: str = ""
    classifier_notes: str = ""
    source: str = "rules"  # rules | llm | merged

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Rule-based preclassification
# --------------------------------------------------------------------------- #
def _best_evidence(mentions: list[dict], prefer_sections: set[str]) -> Optional[dict]:
    """Pick the most informative mention (prefer methods/results sections)."""
    if not mentions:
        return None
    preferred = [m for m in mentions if m.get("section") in prefer_sections and not m.get("is_weak")]
    if preferred:
        return preferred[0]
    nonweak = [m for m in mentions if not m.get("is_weak")]
    if nonweak:
        return nonweak[0]
    return mentions[0]


def rule_preclassify(
    *,
    has_full_text: bool,
    title: str,
    abstract: str,
    mentions: list[dict],
    resource_detected: str,
) -> Classification:
    """Deterministic first pass.

    ``mentions`` are dicts with keys: resource_term, section, sentence_window,
    is_weak. Returns a Classification with ``source='rules'``.
    """
    c = Classification(source="rules", resource_detected_in_text=resource_detected)

    title_l = (title or "").lower()
    is_review = any(h in title_l for h in REVIEW_TITLE_HINTS)

    if not has_full_text:
        # Abstract-only path: only call it data-use if the abstract is explicit.
        abs = abstract or ""
        if abs_says_data_use(abs):
            c.actually_uses_connectome_data = "probably_yes"
            c.use_category = "A_direct_connectome_data_analysis"
            c.use_subcategory = "unknown"
            c.evidence_quote = _first_match_quote(abs, _STRONG_YES) or abs[:300]
            c.evidence_section = "abstract"
            c.confidence = "low"
            c.manual_review_needed = "yes"
            c.manual_review_reason = "data-use inferred from abstract only; no full text"
        else:
            c.actually_uses_connectome_data = "unclear"
            c.use_category = "G_unclassifiable_no_full_text"
            c.manual_review_needed = "yes"
            c.manual_review_reason = "no full text available"
        return c

    # Full text available. Dedupe windows so repeated mentions of the same
    # sentence don't produce duplicated evidence text.
    def _join_unique(ms) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for m in ms:
            w = (m.get("sentence_window", "") or "").strip()
            if w and w not in seen:
                seen.add(w)
                out.append(w)
        return " ".join(out)

    methods_results_text = _join_unique(m for m in mentions if m.get("section") in DATA_USE_SECTIONS)
    all_windows = _join_unique(mentions)

    strong_hit = _first_match_quote(methods_results_text, _STRONG_YES) or _first_match_quote(all_windows, _STRONG_YES)
    nonweak_mentions = [m for m in mentions if not m.get("is_weak")]
    has_method_mention = any(m.get("section") in DATA_USE_SECTIONS for m in nonweak_mentions)
    only_background = bool(nonweak_mentions) and all(
        m.get("section") in {"introduction", "discussion", "references", "unknown"} for m in nonweak_mentions
    )
    only_refs = bool(nonweak_mentions) and all(m.get("section") == "references" for m in nonweak_mentions)

    ev = _best_evidence(mentions, DATA_USE_SECTIONS)
    if ev:
        c.evidence_quote = (ev.get("sentence_window") or "")[:600]
        c.evidence_section = ev.get("section", "unknown")

    if is_review and not strong_hit:
        c.actually_uses_connectome_data = "probably_no"
        c.use_category = "F_review_perspective_commentary"
        c.use_subcategory = "review_only"
        c.confidence = "medium"
        c.manual_review_needed = "no"
        c.manual_review_reason = ""
        return c

    if strong_hit and has_method_mention:
        c.actually_uses_connectome_data = "probably_yes"
        c.use_category = "A_direct_connectome_data_analysis"
        c.use_subcategory = _guess_subcategory(strong_hit)
        c.evidence_quote = strong_hit[:600]
        c.evidence_section = "methods" if c.evidence_section == "unknown" else c.evidence_section
        c.confidence = "medium"
        c.manual_review_needed = "no"
        return c

    if only_refs:
        c.actually_uses_connectome_data = "no"
        c.use_category = "E_background_citation_only"
        c.use_subcategory = "background_only"
        c.confidence = "medium"
        c.manual_review_needed = "no"
        c.manual_review_reason = "resource appears only in references"
        return c

    if only_background and not has_method_mention:
        c.actually_uses_connectome_data = "probably_no"
        c.use_category = "E_background_citation_only"
        c.use_subcategory = "background_only"
        c.confidence = "low"
        c.manual_review_needed = "yes"
        c.manual_review_reason = "mentions only in intro/discussion; verify"
        return c

    # Mentions exist but signals are mixed -> leave for LLM / manual review.
    if nonweak_mentions:
        c.actually_uses_connectome_data = "unclear"
        c.use_category = "B_connectome_derived_biological_result"
        c.use_subcategory = "unknown"
        c.confidence = "low"
        c.manual_review_needed = "yes"
        c.manual_review_reason = "resource mentioned but data-use not established by rules"
        return c

    # No resource mention at all in full text.
    c.actually_uses_connectome_data = "no"
    c.use_category = "E_background_citation_only"
    c.use_subcategory = "background_only"
    c.confidence = "low"
    c.manual_review_needed = "yes"
    c.manual_review_reason = "no resource mention detected in full text"
    return c


def abs_says_data_use(abstract: str) -> bool:
    if not abstract:
        return False
    return any(rx.search(abstract) for rx in _STRONG_YES)


def _first_match_quote(text: str, patterns: list[re.Pattern]) -> Optional[str]:
    if not text:
        return None
    for rx in patterns:
        m = rx.search(text)
        if m:
            # Return the surrounding sentence-ish span.
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 120)
            return text[start:end].strip()
    return None


def _guess_subcategory(quote: str) -> str:
    q = quote.lower()
    if "partner" in q:
        return "synaptic_partner_analysis"
    if "connectivity" in q or "adjacency" in q:
        return "connectivity_query"
    if "model" in q or "simulation" in q:
        return "circuit_model_from_connectome"
    if "skeleton" in q or "mesh" in q or "morpholog" in q:
        return "neuron_id_or_skeleton_use"
    if "cell type" in q or "annotation" in q:
        return "cell_type_annotation_use"
    if "proofread" in q or "benchmark" in q or "segment" in q:
        return "tool_benchmark_on_connectome"
    if "regist" in q or "align" in q:
        return "registration_alignment_to_connectome"
    return "unknown"


# --------------------------------------------------------------------------- #
# Merge logic (rules + LLM)
# --------------------------------------------------------------------------- #
_POS = {"yes", "probably_yes"}
_NEG = {"no", "probably_no"}


def merge_classification(rules: Classification, llm: Optional[Classification], has_full_text: bool) -> Classification:
    """Combine rule and LLM verdicts per the brief's decision table."""
    if not has_full_text:
        out = llm or rules
        out = _copy(out)
        out.use_category = "G_unclassifiable_no_full_text"
        # Preserve an abstract-explicit yes only if evidence quote exists.
        if out.actually_uses_connectome_data in _POS and not out.evidence_quote:
            out.actually_uses_connectome_data = "unclear"
        out.manual_review_needed = "yes"
        if not out.manual_review_reason:
            out.manual_review_reason = "no full text available"
        out.source = "merged"
        return _enforce_evidence_guard(out)

    if llm is None:
        return _enforce_evidence_guard(_copy(rules))

    r = rules.actually_uses_connectome_data
    l = llm.actually_uses_connectome_data

    # Strong agreement.
    if r in _POS and l in _POS:
        out = _copy(llm)
        out.actually_uses_connectome_data = "yes"
        out.confidence = "high"
        out.manual_review_needed = "no"
        out.source = "merged"
        if not out.evidence_quote:
            out.evidence_quote = rules.evidence_quote
        return _enforce_evidence_guard(out)

    if r in _NEG and l in _NEG:
        out = _copy(llm)
        out.actually_uses_connectome_data = "no"
        out.confidence = "high"
        out.manual_review_needed = "no"
        out.source = "merged"
        return out

    # Disagreement.
    if (r in _POS and l in _NEG) or (r in _NEG and l in _POS):
        out = _copy(llm)
        out.actually_uses_connectome_data = "unclear"
        out.confidence = "low"
        out.manual_review_needed = "yes"
        out.manual_review_reason = (
            f"rules({r}) and LLM({l}) disagree"
        )
        out.source = "merged"
        return _enforce_evidence_guard(out)

    # Otherwise defer to the LLM result.
    out = _copy(llm)
    out.source = "merged"
    if out.confidence == "low" and out.manual_review_needed != "yes":
        out.manual_review_needed = "yes"
        out.manual_review_reason = out.manual_review_reason or "low confidence LLM result"
    return _enforce_evidence_guard(out)


def _enforce_evidence_guard(c: Classification) -> Classification:
    """Never allow a 'yes' without an evidence quote (hard quality rule)."""
    if c.actually_uses_connectome_data == "yes" and not (c.evidence_quote or "").strip():
        c.actually_uses_connectome_data = "probably_yes"
        c.confidence = "low"
        c.manual_review_needed = "yes"
        c.manual_review_reason = (c.manual_review_reason + "; ").lstrip("; ") + "yes downgraded: missing evidence quote"
    return c


def _copy(c: Classification) -> Classification:
    return Classification(**c.to_dict())


# --------------------------------------------------------------------------- #
# LLM classification
# --------------------------------------------------------------------------- #
LLM_PROMPT = """You are classifying scientific papers for a bibliometric audit.

Question:
Does this paper materially use Drosophila connectome data/resources, or does it merely cite them as background?

Target resources include hemibrain, FAFB, FlyWire, MANC, FANC, neuPrint, CATMAID, CAVE, Codex, navis/fafbseg, skeletons, meshes, synapse tables, neuron IDs, annotations, and connectivity matrices.

Classify into exactly one category:

A_direct_connectome_data_analysis:
The paper directly queries/analyzes connectome data: synapses, partners, connectivity matrices, neuron IDs, skeletons, meshes, cell annotations, pathways, motifs, simulations based on connectome topology.

B_connectome_derived_biological_result:
The paper relies on previously published connectome-derived annotations, cell types, pathways, or circuit diagrams as a material part of a biological claim.

C_tool_or_method_using_connectome_dataset:
The paper uses a connectome dataset to build, test, benchmark, visualize, align, segment, proofread, search, or model data/tools.

D_reuses_published_stats_or_figures_only:
The paper reuses published counts, screenshots, diagrams, or broad summary statistics, but does not newly analyze or depend on the dataset.

E_background_citation_only:
The paper cites connectome resources only as context/background and does not materially use data.

F_review_perspective_commentary:
The paper is a review, perspective, commentary, or news article without new data use.

G_unclassifiable_no_full_text:
Insufficient full text/evidence to classify.

Return JSON only with these keys:
{
  "actually_uses_connectome_data": "yes|probably_yes|unclear|probably_no|no",
  "use_category": "A_direct_connectome_data_analysis|B_connectome_derived_biological_result|C_tool_or_method_using_connectome_dataset|D_reuses_published_stats_or_figures_only|E_background_citation_only|F_review_perspective_commentary|G_unclassifiable_no_full_text",
  "use_subcategory": "...",
  "resource_detected_in_text": ["..."],
  "evidence_quote": "...",
  "evidence_section": "abstract|introduction|methods|results|discussion|supplement|data_availability|figure_caption|references|unknown",
  "confidence": "high|medium|low",
  "manual_review_needed": "yes|no",
  "manual_review_reason": "...",
  "classifier_notes": "..."
}

Rules:
- Do not classify as yes unless there is textual evidence that data/resources were used.
- Citation alone is not data use.
- A resource named only in references is not data use.
- A review article is not data use unless it performs new analysis.
- If only abstract is available, classify cautiously and mark manual_review_needed=yes unless the abstract explicitly states data use.
- Evidence quote must be copied from provided text, not invented.
"""


def build_user_payload(*, title: str, abstract: str, evidence_windows: list[str],
                       data_availability: str = "", figure_captions: str = "",
                       has_full_text: bool = True) -> str:
    parts = [f"TITLE:\n{title}\n", f"ABSTRACT:\n{abstract or '(none)'}\n"]
    parts.append(f"FULL_TEXT_AVAILABLE: {'yes' if has_full_text else 'no (abstract only)'}\n")
    if evidence_windows:
        joined = "\n---\n".join(w for w in evidence_windows[:25] if w)
        parts.append(f"RESOURCE_MENTION_EVIDENCE_WINDOWS:\n{joined}\n")
    else:
        parts.append("RESOURCE_MENTION_EVIDENCE_WINDOWS:\n(none found)\n")
    if data_availability:
        parts.append(f"DATA_AVAILABILITY:\n{data_availability[:1500]}\n")
    if figure_captions:
        parts.append(f"FIGURE_CAPTIONS_WITH_MENTIONS:\n{figure_captions[:1500]}\n")
    return "\n".join(parts)


def llm_classify(*, title: str, abstract: str, evidence_windows: list[str],
                 data_availability: str = "", figure_captions: str = "",
                 has_full_text: bool = True) -> Optional[Classification]:
    """Call the configured LLM provider. Returns None if no provider/parse fails."""
    provider = SETTINGS.llm_provider
    if provider == "none":
        return None
    user = build_user_payload(
        title=title, abstract=abstract, evidence_windows=evidence_windows,
        data_availability=data_availability, figure_captions=figure_captions,
        has_full_text=has_full_text,
    )
    try:
        if provider == "anthropic":
            raw = _call_anthropic(user)
        else:
            raw = _call_openai(user)
    except Exception as e:  # network/SDK errors -> rules-only fallback
        return None
    return _parse_llm_json(raw)


def _call_anthropic(user: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_key)
    msg = client.messages.create(
        model=SETTINGS.anthropic_model,
        max_tokens=1024,
        system=LLM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")


def _call_openai(user: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=SETTINGS.openai_key)
    resp = client.chat.completions.create(
        model=SETTINGS.openai_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": LLM_PROMPT},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def _parse_llm_json(raw: str) -> Optional[Classification]:
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    rdt = d.get("resource_detected_in_text", "none_detected")
    if isinstance(rdt, list):
        rdt = ";".join(str(x) for x in rdt) if rdt else "none_detected"
    return Classification(
        actually_uses_connectome_data=d.get("actually_uses_connectome_data", "unclear"),
        use_category=d.get("use_category", "G_unclassifiable_no_full_text"),
        use_subcategory=d.get("use_subcategory", "unknown"),
        resource_detected_in_text=rdt or "none_detected",
        evidence_quote=d.get("evidence_quote", "") or "",
        evidence_section=d.get("evidence_section", "unknown"),
        confidence=d.get("confidence", "low"),
        manual_review_needed=d.get("manual_review_needed", "yes"),
        manual_review_reason=d.get("manual_review_reason", "") or "",
        classifier_notes=d.get("classifier_notes", "") or "",
        source="llm",
    )
