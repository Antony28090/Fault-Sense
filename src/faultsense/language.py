"""Language seam for Phase 2 (Tamil/Hindi/English voice and code-mixed text)."""
from __future__ import annotations

from typing import Protocol

from faultsense.diagnosis.schema import DiagnosisResponse


class LanguageLayer(Protocol):
    def to_english(self, text: str) -> tuple[str, str]:
        """Return (English text, detected language code)."""

    def from_english(self, response: DiagnosisResponse, language: str) -> DiagnosisResponse: ...


class IdentityLanguageLayer:
    """Phase 1: English in, English out."""

    def to_english(self, text: str) -> tuple[str, str]:
        return text, "en"

    def from_english(self, response: DiagnosisResponse, language: str) -> DiagnosisResponse:
        return response
