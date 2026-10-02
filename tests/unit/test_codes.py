import pytest

from faultsense.codes import (
    bracket_labels,
    code_key,
    code_like_tokens,
    confusable_variants,
    is_code_like,
    label_key,
    query_code_candidates,
)


@pytest.mark.parametrize(
    "raw,key",
    [
        ("OHF", "OHF"), ("ohf", "OHF"), (" InFI ", "INFI"), ("CFI\n(1)", "CFI"),
        ("DRC–", "DRC"), ("MOA-", "MOA"), ("----", "----"), ("COM.E", "COM.E"),
        ("A-17", "A-17"), ("blF", "BLF"),
    ],
)
def test_code_key(raw, key):
    assert code_key(raw) == key


def test_confusable_variants_cover_display_lookalikes():
    assert "OLF" in confusable_variants("0LF")
    assert "INFI" in confusable_variants("INF1")
    assert "SCF5" in confusable_variants("SCFS")
    assert "OHF" not in confusable_variants("OHF")


def test_confusable_variants_never_fold_b_8_or_g_6():
    assert "INF8" not in confusable_variants("INFB")
    assert "INF6" not in confusable_variants("INFG")


@pytest.mark.parametrize(
    "token,expected",
    [
        ("OHF", True), ("SCF1", True), ("tFr", True), ("blF", True), ("InFI", True),
        ("kW", True), ("S3", True), ("A-17", True), ("Check", False), ("motor", False),
        ("phf", False), ("I", False),
    ],
)
def test_is_code_like(token, expected):
    assert is_code_like(token) is expected


def test_code_like_tokens_ignore_sentence_punctuation():
    assert code_like_tokens("Check [Current Limitation] CLI. Then reset OHF.") == ["CLI", "OHF"]


def test_bracket_labels_and_label_keys():
    assert bracket_labels("Set [Current Limitation] CLI and [Motor  data] MOA–") == [
        "Current Limitation", "Motor  data",
    ]
    assert label_key("[Motor  Data]") == "motor data"


def test_query_code_candidates_keep_punctuated_and_dotted_codes():
    assert "OHF" in query_code_candidates("Drive shows OHF.")
    assert "0hf" in query_code_candidates("(0hf) again")
    assert "COM.E" in query_code_candidates("keypad says COM.E")
    assert "is" not in query_code_candidates("it is hot")


def test_query_code_candidates_split_hyphens_and_join_spaced_digits():
    candidates = query_code_candidates("OHF-fault and SCF 1 on keypad A-17")
    assert {"OHF", "SCF1", "A-17"} <= set(candidates)
