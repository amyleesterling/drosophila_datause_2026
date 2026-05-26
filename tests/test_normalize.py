import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from droso_audit.normalize import (
    dedupe_key,
    normalize_doi,
    normalize_pmcid,
    normalize_pmid,
    normalize_title,
    record_id_for,
)


def test_doi_url_and_bare_dedupe_to_same():
    a = normalize_doi("https://doi.org/10.7554/eLife.57443")
    b = normalize_doi("10.7554/eLife.57443")
    c = normalize_doi("doi:10.7554/eLife.57443.")
    assert a == b == c == "10.7554/elife.57443"


def test_doi_none_for_garbage():
    assert normalize_doi("") is None
    assert normalize_doi("nan") is None
    assert normalize_doi("not a doi") is None


def test_doi_trailing_punctuation_stripped():
    assert normalize_doi("10.1016/j.cell.2018.06.019),") == "10.1016/j.cell.2018.06.019"


def test_pmid_and_pmcid():
    assert normalize_pmid("PMID: 12345") == "12345"
    assert normalize_pmcid("PMC123456") == "PMC123456"
    assert normalize_pmcid("123456") == "PMC123456"


def test_title_normalization():
    assert normalize_title("A Connectome & Analysis of the Adult Drosophila!") == \
        "a connectome and analysis of the adult drosophila"


def test_record_id_stable_for_same_doi():
    r1 = record_id_for(doi="https://doi.org/10.7554/eLife.57443")
    r2 = record_id_for(doi="10.7554/eLife.57443")
    assert r1 == r2


def test_dedupe_key_prefers_doi():
    row = {"doi_normalized": "10.x/y", "pmid": "99", "title": "t"}
    assert dedupe_key(row) == "doi_normalized:10.x/y"
    row2 = {"doi_normalized": None, "pmid": "99", "title": "t"}
    assert dedupe_key(row2) == "pmid:99"
