from faultsense.diagnosis.schema import Cause, DiagnosisResponse, Meta, SafetyWarning, Step
from faultsense.language import IdentityLanguageLayer, IndicLanguageLayer
from faultsense.translation import MARKER_RE, FakeTranslator


def english(text, source, target):
    """Fake indic->en: keeps the markers, as a good model would."""
    return "pump drive shows " + " ".join(MARKER_RE.findall(text)) if target == "en" else f"{target}: {text}"


def answer(causes=("Device temperature too high.",), steps=("Clean the heat sink.",),
           warnings=("Wait 15 minutes for the DC bus to discharge.",)):
    return DiagnosisResponse(
        status="diagnosis", query="q", machine_id=None, language="ta", matched_fault_codes=[],
        probable_causes=[Cause(rank=n, cause=c, confidence=0.8, citations=[]) for n, c in enumerate(causes, 1)],
        corrective_actions=[Step(step=n, action=s, requires_isolation=False, citations=[]) for n, s in enumerate(steps, 1)],
        safety_warnings=[SafetyWarning(text=w, citations=[]) for w in warnings],
        escalation=None, sources=[], meta=Meta(retrieval_top_score=1.0),
    )


def test_english_questions_are_not_sent_to_the_translator():
    translator = FakeTranslator(english)
    layer = IndicLanguageLayer(translator)
    assert layer.to_english("OHF on the pump") == ("OHF on the pump", "en")
    assert layer.detect("OHF on the pump") == "en" and translator.calls == []


def test_a_tamil_question_is_translated_with_its_code_kept():
    translator = FakeTranslator(english)
    text_en, language = IndicLanguageLayer(translator).to_english("டிஸ்ப்ளேயில் OHF error வருது")
    assert (text_en, language) == ("pump drive shows OHF", "ta")
    [(sent, source, target)] = translator.calls
    assert (source, target) == ("ta", "en") and "OHF" not in sent[0]


def test_a_long_question_is_translated_sentence_by_sentence():
    translator = FakeTranslator(english)
    IndicLanguageLayer(translator).to_english("पंप बंद है। डिस्प्ले पर OHF है। पंखा नहीं चलता।")
    assert len(translator.calls[0][0]) == 3


def test_a_failed_question_translation_falls_back_to_the_original_text():
    question = "पंप पर OHF"
    assert IndicLanguageLayer(FakeTranslator(error=RuntimeError("down"))).to_english(question) == (question, "hi")
    dropper = FakeTranslator(lambda text, source, target: "pump drive")  # lost the OHF marker
    assert IndicLanguageLayer(dropper).to_english(question) == (question, "hi")


def test_the_answer_is_translated_item_by_item_and_english_is_kept():
    response = IndicLanguageLayer(FakeTranslator(english)).from_english(answer(), "ta")
    tr = response.translation
    assert (tr.language, tr.available) == ("ta", True)
    assert [t.text for t in tr.causes] == ["ta: Device temperature too high."]
    assert [t.text for t in tr.steps] == ["ta: Clean the heat sink."]
    assert tr.safety_warnings[0].text == "ta: Wait 15 minutes for the DC bus to discharge."
    assert response.probable_causes[0].cause == "Device temperature too high."  # English untouched


def test_a_sentence_that_loses_a_marker_or_comes_back_blank_is_shown_in_english():
    def flaky(text, source, target):
        if "heat sink" in text:
            return "   "
        return MARKER_RE.sub("", text) if MARKER_RE.search(text) else f"{target}: {text}"

    tr = IndicLanguageLayer(FakeTranslator(flaky)).from_english(answer(), "hi").translation
    assert tr.causes[0].fallback is False
    assert (tr.steps[0].text, tr.steps[0].fallback) == ("Clean the heat sink.", True)
    assert (tr.safety_warnings[0].text, tr.safety_warnings[0].fallback) == (
        "Wait 15 minutes for the DC bus to discharge.", True)


def test_an_unavailable_translator_leaves_the_english_answer_and_says_why():
    response = IndicLanguageLayer(FakeTranslator(error=OSError("model files missing"))).from_english(answer(), "hi")
    assert response.translation.available is False and "model files missing" in response.translation.note
    assert response.translation.causes == [] and response.probable_causes[0].cause == "Device temperature too high."


def test_english_answers_and_empty_escalations():
    translator = FakeTranslator(english)
    layer = IndicLanguageLayer(translator)
    assert layer.from_english(answer(), "en").translation is None
    empty = layer.from_english(answer(causes=(), steps=(), warnings=()), "ta")
    assert empty.translation.available is True and empty.translation.causes == []
    assert translator.calls == []


def test_identity_layer_detects_nothing():
    assert IdentityLanguageLayer().detect("पंप पर OHF") == "en"


def test_the_answers_fault_codes_survive_translation_in_any_case():
    from faultsense.diagnosis.schema import MatchedCode

    response = answer(causes=("Input phase loss phf.",), steps=("Repeat the autotuning after tnf.",), warnings=())
    response.matched_fault_codes = [MatchedCode(code="PHF", manual="atv320", name="Input Phase Loss", page=415, fuzzy=False)]
    response.probable_causes[0].fault_code = "TNF"
    transliterate = FakeTranslator(lambda text, source, target: text.replace("phf", "पीएचएफ").replace("tnf", "टीएनएफ"))
    tr = IndicLanguageLayer(transliterate).from_english(response, "hi").translation
    assert (tr.causes[0].text, tr.steps[0].text) == ("Input phase loss phf.", "Repeat the autotuning after tnf.")
