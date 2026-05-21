import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from droso_audit.classify import (
    Classification,
    merge_classification,
    rule_preclassify,
)


def _mention(term, section, window, weak=False):
    return {"resource_term": term, "section": section, "sentence_window": window, "is_weak": weak}


def test_strong_yes_in_methods():
    m = [_mention("hemibrain", "methods",
                  "We used the hemibrain connectome to identify synaptic partners.")]
    c = rule_preclassify(has_full_text=True, title="A circuit study",
                         abstract="", mentions=m, resource_detected="hemibrain")
    assert c.actually_uses_connectome_data == "probably_yes"
    assert c.use_category == "A_direct_connectome_data_analysis"
    assert c.evidence_quote


def test_background_only_in_intro():
    m = [_mention("hemibrain", "introduction",
                  "Recent connectomes such as hemibrain have transformed neuroscience.")]
    c = rule_preclassify(has_full_text=True, title="Some study",
                         abstract="", mentions=m, resource_detected="hemibrain")
    assert c.actually_uses_connectome_data in ("probably_no", "no")
    assert c.use_category == "E_background_citation_only"


def test_references_only_is_no():
    m = [_mention("FlyWire", "references", "Dorkenwald et al. FlyWire ...")]
    c = rule_preclassify(has_full_text=True, title="x", abstract="",
                         mentions=m, resource_detected="FlyWire")
    assert c.actually_uses_connectome_data == "no"


def test_review_title():
    m = [_mention("FlyWire", "introduction", "FlyWire and hemibrain are recent connectomes.")]
    c = rule_preclassify(has_full_text=True, title="A review of fly connectomics",
                         abstract="", mentions=m, resource_detected="FlyWire")
    assert c.use_category == "F_review_perspective_commentary"


def test_no_full_text_is_unclassifiable():
    c = rule_preclassify(has_full_text=False, title="x", abstract="",
                         mentions=[], resource_detected="none_detected")
    assert c.use_category == "G_unclassifiable_no_full_text"
    assert c.manual_review_needed == "yes"


def test_abstract_explicit_data_use():
    c = rule_preclassify(has_full_text=False, title="x",
                         abstract="Here we used the FlyWire connectome to map a circuit.",
                         mentions=[], resource_detected="FlyWire")
    assert c.actually_uses_connectome_data == "probably_yes"
    assert c.manual_review_needed == "yes"


def test_merge_agreement_yes_high():
    rules = Classification(actually_uses_connectome_data="probably_yes",
                           use_category="A_direct_connectome_data_analysis",
                           evidence_quote="we used the hemibrain connectome")
    llm = Classification(actually_uses_connectome_data="yes",
                         use_category="A_direct_connectome_data_analysis",
                         evidence_quote="we used the hemibrain connectome")
    out = merge_classification(rules, llm, has_full_text=True)
    assert out.actually_uses_connectome_data == "yes"
    assert out.confidence == "high"
    assert out.manual_review_needed == "no"


def test_merge_disagreement_unclear():
    rules = Classification(actually_uses_connectome_data="no",
                           use_category="E_background_citation_only")
    llm = Classification(actually_uses_connectome_data="yes",
                         use_category="A_direct_connectome_data_analysis",
                         evidence_quote="q")
    out = merge_classification(rules, llm, has_full_text=True)
    assert out.actually_uses_connectome_data == "unclear"
    assert out.manual_review_needed == "yes"


def test_yes_without_evidence_downgraded():
    rules = Classification(actually_uses_connectome_data="yes", evidence_quote="")
    llm = Classification(actually_uses_connectome_data="yes", evidence_quote="")
    out = merge_classification(rules, llm, has_full_text=True)
    assert out.actually_uses_connectome_data != "yes"  # guard kicks in
    assert out.manual_review_needed == "yes"


def test_no_full_text_yes_requires_evidence():
    rules = Classification(actually_uses_connectome_data="probably_yes", evidence_quote="")
    out = merge_classification(rules, None, has_full_text=False)
    assert out.use_category == "G_unclassifiable_no_full_text"
    assert out.actually_uses_connectome_data == "unclear"
