"""Language seam: Hindi and Tamil questions in, translated answers out; English stays the master copy."""
from __future__ import annotations

from typing import Protocol

from faultsense.diagnosis.schema import AnswerTranslation, DiagnosisResponse, TranslatedText
from faultsense.translation import Translator, detect_script, translate_shielded


class LanguageLayer(Protocol):
    def detect(self, text: str) -> str:
        """The language code of the text's script ("en", "hi" or "ta")."""

    def to_english(self, text: str) -> tuple[str, str]:
        """Return (English text, detected language code)."""

    def from_english(self, response: DiagnosisResponse, language: str) -> DiagnosisResponse: ...


class IdentityLanguageLayer:
    """No translation (TRANSLATION=off): English in, English out."""

    def detect(self, text: str) -> str:
        return "en"

    def to_english(self, text: str) -> tuple[str, str]:
        return text, "en"

    def from_english(self, response: DiagnosisResponse, language: str) -> DiagnosisResponse:
        return response


class IndicLanguageLayer:
    """Hindi and Tamil through a Translator, with codes, names, numbers and pages shielded.

    Translation never blocks a diagnosis: a failed question is searched as typed, and a failed answer
    stays English with `translation.available = False`.
    """

    def __init__(self, translator: Translator):
        self._translator = translator

    def detect(self, text: str) -> str:
        return detect_script(text)

    def to_english(self, text: str) -> tuple[str, str]:
        language = detect_script(text)
        if language == "en":
            return text, "en"
        try:
            [english] = translate_shielded(self._translator, [text], language, "en")
        except Exception:  # translation must never block a diagnosis
            return text, language
        return (english, language) if english else (text, language)

    def from_english(self, response: DiagnosisResponse, language: str) -> DiagnosisResponse:
        if language not in ("hi", "ta"):
            return response
        causes = [c.cause for c in response.probable_causes]
        steps = [s.action for s in response.corrective_actions]
        warnings = [w.text for w in response.safety_warnings]
        texts = causes + steps + warnings
        codes = [m.code for m in response.matched_fault_codes] + [c.fault_code for c in response.probable_causes
                                                                  if c.fault_code]
        try:
            results = translate_shielded(self._translator, texts, "en", language, codes) if texts else []
        except Exception as exc:
            response.translation = AnswerTranslation(language=language, available=False,
                                                     note=f"{type(exc).__name__}: {exc}"[:300])
            return response
        items = [TranslatedText(text=r if r is not None else original, fallback=r is None)
                 for original, r in zip(texts, results)]
        response.translation = AnswerTranslation(
            language=language, available=True,
            causes=items[:len(causes)], steps=items[len(causes):len(causes) + len(steps)],
            safety_warnings=items[len(causes) + len(steps):],
        )
        return response
