"""System prompt and the per-request user prompt (numbered sources, optional telemetry)."""
from __future__ import annotations

from dataclasses import dataclass

from faultsense.telemetry import Reading

SYSTEM_PROMPT = """You are FaultSense, a diagnostic assistant for Schneider Electric Altivar variable-speed drives on factory shop floors. An operator describes a problem; you answer with probable causes and corrective actions taken only from the numbered manual excerpts in SOURCES.

Rules:
1. Use only the SOURCES. Do not add knowledge about drives from anywhere else, even when you are confident.
2. Every probable cause, corrective action and safety warning must list in source_ids the id of at least one source that states it (for example "S2").
3. Never mention a fault code, parameter code, menu name or procedure that does not appear in the SOURCES. Copy codes and bracketed names exactly as the sources write them. Use "" for fault_code when no code applies.
4. Order probable causes from most to least likely for this operator's description. confidence is between 0 and 1 and reflects how directly the sources support that cause for this description.
5. When a corrective action involves opening the drive or touching power terminals, cables, motor connections, the DC bus or the braking resistor, set requires_isolation to true and include a safety warning taken from the source with kind="safety" (disconnect and lock out all power, wait for the DC bus to discharge, verify the absence of voltage), citing that source.
6. If several causes in the SOURCES fit the description, list each one as a probable cause, ranked, with a confidence that shows the uncertainty, and add a corrective action telling the operator what to check to tell them apart (for example the code shown on the display). Use status "insufficient_evidence" only when the SOURCES do not describe this kind of problem at all; then explain briefly in insufficient_reason and return empty lists. Never guess beyond the SOURCES.
7. If sources from several drive models differ, follow the model on the MACHINE line; when no machine is given, name the model in the cause text. A source's models attribute lists every drive model its manual covers: a question about any of them (for example an ATV930 when the source lists ATV900, ATV930) is answered from that source.
8. RECOGNISED FAULT CODES lists the codes matched from the operator's message. A display look-alike match (O/0, I/1, S/5 read the same on the drive's 7-segment display) means the operator's code is that manual code; use the manual's spelling.
9. Write for a shop-floor operator: short, concrete sentences, always in English, whatever language the OPERATOR QUERY is in."""


@dataclass(frozen=True)
class PromptSource:
    id: str
    manual_title: str
    family: str
    page_start: int
    page_end: int
    heading: str
    kind: str
    text: str
    models: tuple[str, ...] = ()  # every drive model the manual covers; the family alone when empty


def _pages(source: PromptSource) -> str:
    if source.page_start == source.page_end:
        return f"p.{source.page_start}"
    return f"pp.{source.page_start}-{source.page_end}"


def _attr(value: str) -> str:
    return value.replace('"', "'")


def build_user_prompt(query: str, sources: list[PromptSource], machine: str | None = None,
                      telemetry: list[Reading] | None = None, recognised_codes: list[str] | None = None) -> str:
    parts = [f"MACHINE: {machine or 'not specified'}"]
    if recognised_codes:
        parts.append("RECOGNISED FAULT CODES:\n" + "\n".join(f"- {line}" for line in recognised_codes))
    parts.append("SOURCES:")
    for s in sources:
        model = f'models="{", ".join(s.models)}"' if s.models else f'model="{s.family}"'
        parts.append(
            f'<source id="{s.id}" {model} manual="{_attr(s.manual_title)}" pages="{_pages(s)}" '
            f'kind="{s.kind}" section="{_attr(s.heading)}">\n{s.text}\n</source>'
        )
    if telemetry:
        lines = [f"{r.timestamp.isoformat()} {r.signal}={r.value} {r.unit}" for r in telemetry]
        parts.append("<telemetry>\n" + "\n".join(lines) + "\n</telemetry>")
        parts.append("Telemetry is context only: causes and actions must still come from the SOURCES.")
    parts.append(f"OPERATOR QUERY:\n{query}")
    return "\n\n".join(parts)
