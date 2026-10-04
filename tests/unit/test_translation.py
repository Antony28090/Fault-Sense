import pytest

from faultsense.translation import (
    MARKER_RE, FakeTranslator, detect_script, restore, shield, split_sentences, translate_shielded,
)


@pytest.mark.parametrize("text, language", [
    ("OHF on the pump", "en"),
    ("बोरवेल पंप की ड्राइव पर OHF आ रहा है", "hi"),
    ("போர்வெல் பம்ப் டிரைவில் OHF வருகிறது", "ta"),
    ("டிஸ்ப்ளேயில் OHF error வருது", "ta"),
    ("motor ka current bahut zyada hai", "en"),  # romanised Hinglish stays on the English path
    ("", "en"),
])
def test_detect_script(text, language):
    assert detect_script(text) == language


def test_shield_hides_every_protected_kind_and_restore_puts_it_back():
    text = "Wait 15 minutes, measure the DC bus (below 42 Vdc), set [Brake release freq] and check OHF on p.672."
    masked, tokens = shield(text)
    for protected in ["15 minutes", "DC", "42 Vdc", "[Brake release freq]", "OHF", "p.672"]:
        assert protected in tokens and protected not in masked
    assert len(set(MARKER_RE.findall(masked))) == len(tokens)
    assert restore(masked, tokens) == text


def test_restore_accepts_reordered_markers_and_attached_suffixes():
    masked, tokens = shield("OHF appears after 10 minutes")
    first, second = MARKER_RE.findall(masked)
    assert restore(f"{second} के बाद {first}को देखें", tokens) == "10 minutes के बाद OHFको देखें"


def test_restore_rejects_lost_doubled_or_invented_markers():
    masked, tokens = shield("Check OHF and SCF1")
    a, b = MARKER_RE.findall(masked)
    assert restore(f"{a} जाँचें", tokens) is None
    assert restore(f"{a} {a} {b}", tokens) is None
    assert restore(f"{a} {b} ZQP", tokens) is None


def test_ranges_and_adjacent_markers_round_trip():
    masked, tokens = shield("Wait 10-20 minutes")
    assert restore(masked, tokens) == "Wait 10-20 minutes"
    masked, tokens = shield("OHF SCF1")
    a, b = MARKER_RE.findall(masked)
    assert restore(f"{a}{b}", tokens) == "OHFSCF1"


def test_split_sentences_keeps_each_sentence():
    assert split_sentences("Pump trips. It is hot!  Fan noisy? पंप बंद है। ठीक\nnext") == [
        "Pump trips.", "It is hot!", "Fan noisy?", "पंप बंद है।", "ठीक", "next"]


def test_translate_shielded_sends_masked_sentences_and_restores_them():
    translator = FakeTranslator(lambda text, source, target: f"<{target}> {text}")
    [result] = translate_shielded(translator, ["Check OHF. Wait 15 minutes."], "en", "hi")
    assert result == "<hi> Check OHF. <hi> Wait 15 minutes."
    [(sent, source, target)] = translator.calls
    assert (source, target) == ("en", "hi") and len(sent) == 2
    assert all("OHF" not in s and "15" not in s for s in sent)


def test_translate_shielded_marks_lost_markers_and_blank_output_as_none():
    dropper = FakeTranslator(lambda text, source, target: MARKER_RE.sub("", text))
    assert translate_shielded(dropper, ["Check OHF"], "en", "ta") == [None]
    blank = FakeTranslator(lambda text, source, target: "   ")
    assert translate_shielded(blank, ["Clean the heat sink."], "en", "ta") == [None]


def test_fake_translator_can_raise():
    with pytest.raises(RuntimeError):
        translate_shielded(FakeTranslator(error=RuntimeError("down")), ["x"], "en", "hi")


def test_markers_spelled_out_in_hindi_letters_are_mapped_back():
    def spelled(text, source, target):  # what IndicTrans2 did to a sentence-initial marker in the trial
        return text.replace("ZQA", "जेड. क्यू. ए.").replace("ZQB", "जेड क्यू बी")

    [result] = translate_shielded(FakeTranslator(spelled), ["Measure the DC bus terminals, below 42 Vdc."], "en", "hi")
    assert result is not None and "DC" in result and "42 Vdc" in result and "जेड" not in result


def test_setup_commands_create_the_environment_only_when_missing(tmp_path):
    from faultsense.translation import setup_commands

    python = tmp_path / ".venv-indic" / "Scripts" / "python.exe"
    labels = [label for label, _ in setup_commands(python)]
    assert labels[0].startswith("Creating") and len(labels) == 3
    python.parent.mkdir(parents=True)
    python.write_text("")
    assert [label for label, _ in setup_commands(python)][0].startswith("Installing")


def test_a_blank_sentence_inside_an_item_makes_the_whole_item_fall_back():
    drops_second = FakeTranslator(lambda text, source, target: "" if text.startswith("Hazardous") else f"{target}: {text}")
    assert translate_shielded(drops_second, ["Disconnect all power. Hazardous voltage remains."], "en", "hi") == [None]


def test_hyphenated_codes_are_shielded_whole_and_negative_numbers_still_shield():
    masked, tokens = shield("A-17 appears at -10 °C")
    assert "A-17" in tokens and "10 °C" in tokens and "A-" not in masked


def test_the_answers_own_codes_are_shielded_whatever_their_case():
    masked, tokens = shield("[Input Phase Loss] phf: check the fuses.", codes=["PHF"])
    assert "phf" in tokens and "phf" not in masked
    transliterate = FakeTranslator(lambda text, source, target: text.replace("tnf", "टीएनएफ"))
    assert translate_shielded(transliterate, ["Autotuning stopped on tnf."], "en", "hi", codes=["TNF"]) == [
        "Autotuning stopped on tnf."]
