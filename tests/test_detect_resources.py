import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from droso_audit.detect_resources import detect_mentions, resources_detected


def test_detects_hemibrain_and_neuprint():
    text = "We queried the hemibrain connectome using neuPrint to find partners."
    m = detect_mentions(text, section="methods")
    labels = {x.resource_term for x in m if not x.is_weak}
    assert "hemibrain" in labels
    assert "neuPrint" in labels


def test_detects_flywire_and_codex():
    text = "Data were downloaded from FlyWire via Codex (codex.flywire.ai)."
    labels = {x.resource_term for x in detect_mentions(text, "methods") if not x.is_weak}
    assert "FlyWire" in labels
    assert "Codex" in labels


def test_weak_terms_flagged():
    text = "We computed a connectivity matrix from synaptic partners."
    m = detect_mentions(text, "methods")
    assert any(x.is_weak for x in m)


def test_no_false_positive_on_empty():
    assert detect_mentions("", "methods") == []
    assert resources_detected([]) == "none_detected"


def test_fafb_variants():
    for t in ["FAFB", "FAFB14", "FAFB v14", "full adult fly brain"]:
        labels = {x.resource_term for x in detect_mentions(t, "methods") if not x.is_weak}
        assert "FAFB" in labels, t


def test_sentence_window_includes_context():
    text = "Intro sentence one. We used the FlyWire connectome here. A following sentence."
    m = [x for x in detect_mentions(text, "methods") if x.resource_term == "FlyWire"][0]
    assert "We used the FlyWire connectome" in m.sentence_window
