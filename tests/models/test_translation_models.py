"""Real IndicTrans2 weights: protected text survives both directions."""
import pytest

from faultsense.config import get_settings
from faultsense.translation import translate_shielded
from faultsense.wiring import build_translator

pytestmark = pytest.mark.models


@pytest.fixture(scope="module")
def translator():
    settings = get_settings()
    if not settings.translation_python_path.exists():
        pytest.skip("run `faultsense setup-translation` first")
    translator = build_translator(settings)
    yield translator
    translator.close()


@pytest.mark.parametrize("language", ["hi", "ta"])
def test_answer_sentences_keep_codes_numbers_and_names(translator, language):
    texts = ["Disconnect all power and wait 15 minutes for the DC bus capacitors to discharge.",
             "Check the setting of [Brake release freq] when the drive shows BLF."]
    results = translate_shielded(translator, texts, "en", language)
    assert all(results), results
    assert "15 minutes" in results[0] and "[Brake release freq]" in results[1] and "BLF" in results[1]


@pytest.mark.parametrize("question", ["बोरवेल पंप की ड्राइव पर OHF आ रहा है", "போர்வெல் பம்ப் டிரைவில் OHF வருகிறது"])
def test_questions_reach_english_with_the_code(translator, question):
    from faultsense.translation import detect_script

    [english] = translate_shielded(translator, [question], detect_script(question), "en")
    assert english and "OHF" in english
