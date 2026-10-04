"""Translation between English and Hindi/Tamil with safety-critical text shielded from the model.

Codes, parameter names, bracketed manual names, page references and numbers with units must come out
exactly as they went in. shield() swaps them for markers before translation and restore() puts them
back, returning None when the model lost, doubled or invented a marker so the caller can show English.
"""
from __future__ import annotations

import atexit
import json
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Iterable, Protocol

from faultsense.codes import LABEL_RE, TOKEN_RE, code_key, is_code_like

LANGUAGES = ("en", "hi", "ta")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_TAMIL = re.compile(r"[஀-௿]")

# Marker format chosen by the plan's trial: copied through unchanged most reliably. Labels use A-P only,
# so two adjacent markers ("ZQAZQB") still split cleanly.
MARKER_PREFIX = "ZQ"
_LETTERS = "ABCDEFGHIJKLMNOP"
MARKER_RE = re.compile(MARKER_PREFIX + "[A-P]+")
_PAGE_RE = re.compile(r"\bpp?\.\s?\d+(?:\s?[-–]\s?\d+)?")
_UNITS = r"%|°C|°F|minutes?|mins?|seconds?|hours?|ms|s|h|Vdc|VDC|Vac|VAC|kV|V|mA|A|kHz|Hz|kW|W|ohms?|Ω|rpm|mm|m"
# Not after "letter-": the number in a code such as A-17 stays with its code.
_NUMBER_RE = re.compile(rf"(?<![\w.])(?<![A-Za-z]-)\d+(?:[.,]\d+)?(?:\s?(?:{_UNITS})(?![A-Za-z]))?")
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+|\n+")
_HINDI_LETTERS = {"ए": "A", "बी": "B", "सी": "C", "डी": "D", "ई": "E", "एफ": "F", "जी": "G", "एच": "H",
                  "आई": "I", "जे": "J", "के": "K", "एल": "L", "एम": "M", "एन": "N", "ओ": "O", "पी": "P"}
_SPELLED_MARKER_RE = re.compile(
    r"जेड\.?\s*क्यू\.?\s*(" + "|".join(sorted(map(re.escape, _HINDI_LETTERS), key=len, reverse=True)) + r")\.?")


def detect_script(text: str) -> str:
    """"hi" for Devanagari, "ta" for Tamil script, else "en" (including romanised Hinglish/Tanglish)."""
    devanagari = len(_DEVANAGARI.findall(text))
    tamil = len(_TAMIL.findall(text))
    if not devanagari and not tamil:
        return "en"
    return "hi" if devanagari >= tamil else "ta"


def _marker(index: int) -> str:
    label = ""
    while True:
        label = _LETTERS[index % 16] + label
        index //= 16
        if index == 0:
            return MARKER_PREFIX + label


def shield(text: str, codes: Iterable[str] = ()) -> tuple[str, list[str]]:
    """`codes` are shielded whatever their case: the manuals print some codes in lowercase (ATV320 `phf`),
    which do not look like codes on their own."""
    tokens: list[str] = []
    keys = {code_key(code) for code in codes if code}

    def keep(original: str) -> str:
        tokens.append(original)
        return _marker(len(tokens) - 1)

    def protect(token: str) -> str:
        if MARKER_RE.search(token) or not (is_code_like(token) or code_key(token) in keys):
            return token
        return keep(token)

    text = LABEL_RE.sub(lambda m: keep(m.group(0)), text)
    text = _PAGE_RE.sub(lambda m: keep(m.group(0)), text)
    text = _NUMBER_RE.sub(lambda m: keep(m.group(0)), text)
    text = TOKEN_RE.sub(lambda m: protect(m.group(0)), text)
    return text, tokens


def restore(translated: str, tokens: list[str]) -> str | None:
    expected = [_marker(i) for i in range(len(tokens))]
    if sorted(MARKER_RE.findall(translated)) != sorted(expected):
        return None
    lookup = dict(zip(expected, tokens))
    return MARKER_RE.sub(lambda m: lookup[m.group(0)], translated)


def _unspell_markers(text: str) -> str:
    return _SPELLED_MARKER_RE.sub(lambda m: MARKER_PREFIX + _HINDI_LETTERS[m.group(1)], text)


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text) if part and part.strip()]


class Translator(Protocol):
    def translate(self, texts: list[str], source: str, target: str) -> list[str]: ...


def translate_shielded(translator: Translator, texts: list[str], source: str, target: str,
                       codes: Iterable[str] = ()) -> list[str | None]:
    """Each text translated sentence by sentence with its protected parts (and `codes`) shielded; None where
    a marker was lost or any of its sentences came back blank."""
    codes = list(codes)
    shielded = [shield(text, codes) for text in texts]
    segments: list[str] = []
    owners: list[int] = []
    for index, (masked, _) in enumerate(shielded):
        for segment in split_sentences(masked):
            segments.append(segment)
            owners.append(index)
    outputs = translator.translate(segments, source, target) if segments else []
    if len(outputs) != len(segments):
        raise ValueError(f"translator returned {len(outputs)} texts for {len(segments)}")
    parts: list[list[str]] = [[] for _ in texts]
    for owner, output in zip(owners, outputs):
        parts[owner].append(output.strip())
    results: list[str | None] = []
    for (_, tokens), pieces in zip(shielded, parts):
        if not pieces or not all(pieces):  # a blank sentence would silently shorten the text
            results.append(None)
            continue
        restored = restore(_unspell_markers(" ".join(pieces)), tokens)
        results.append(restored if restored and restored.strip() else None)
    return results


class FakeTranslator:
    """Test double: applies `fn(text, source, target)` to each text, or raises `error`; records calls."""

    def __init__(self, fn: Callable[[str, str, str], str] | None = None, error: Exception | None = None):
        self._fn = fn or (lambda text, source, target: f"{target}: {text}")
        self._error = error
        self.calls: list[tuple[list[str], str, str]] = []

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        self.calls.append((list(texts), source, target))
        if self._error:
            raise self._error
        return [self._fn(text, source, target) for text in texts]


# Versions verified by the plan's trial on Windows: IndicTrans2's model code needs transformers 4.
TRANSLATION_REQUIREMENTS = ["transformers==4.57.6", "sentencepiece>=0.2", "indictranstoolkit==1.1.1"]


def setup_commands(python: Path) -> list[tuple[str, list[str]]]:
    """Commands that build the separate translation environment whose interpreter is `python`."""
    python = Path(python)
    commands: list[tuple[str, list[str]]] = []
    if not python.exists():
        commands.append(("Creating the translation environment",
                         [sys.executable, "-m", "venv", str(python.parent.parent)]))
    commands.append(("Installing PyTorch for the CPU",
                     [str(python), "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"]))
    commands.append(("Installing IndicTrans2's libraries",
                     [str(python), "-m", "pip", "install", *TRANSLATION_REQUIREMENTS]))
    return commands


class IndicTrans2Translator:
    """AI4Bharat IndicTrans2 (MIT licence, gated on Hugging Face) in a helper process.

    The models need transformers 4 and IndicTransToolkit, FaultSense needs transformers 5, so they run in
    the separate `.venv-indic` environment (`faultsense setup-translation`) through `indic_worker.py`.
    The helper starts on the first translation, answers one request at a time, stops after `idle_minutes`
    without a request and when FaultSense exits, and starts again when needed.
    """

    def __init__(self, python: str | Path, token: str | None = None, device: str = "cpu",
                 idle_minutes: float = 15.0, timeout: float = 180.0, worker: str | Path | None = None,
                 beams: int = 1):
        self._python = str(python)
        self._token = token
        self._device = device
        self._beams = beams  # greedy: 2.5x faster than 5 beams on the CPU, same protection-check pass rate
        self._idle = idle_minutes * 60
        self._timeout = timeout
        self._worker = str(worker or Path(__file__).with_name("indic_worker.py"))
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._replies: queue.Queue | None = None
        self._timer: threading.Timer | None = None
        self._generation = 0
        atexit.register(self.close)

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        if source == target or not texts:
            return list(texts)
        with self._lock:
            self._generation += 1
            if self._timer:
                self._timer.cancel()
            if self._process is None or self._process.poll() is not None:
                self._start()
            request = json.dumps({"texts": list(texts), "source": source, "target": target}, ensure_ascii=False)
            try:
                self._process.stdin.write(request + "\n")
                self._process.stdin.flush()
                line = self._replies.get(timeout=self._timeout)
            except queue.Empty:
                self._stop()
                raise RuntimeError(f"translation timed out after {self._timeout:.0f} s") from None
            except OSError as exc:
                self._stop()
                raise RuntimeError(f"translation helper stopped: {exc}") from exc
            if line is None:
                self._stop()
                raise RuntimeError("translation helper stopped unexpectedly")
            try:
                reply = json.loads(line)
            except ValueError:
                reply = None
            if not isinstance(reply, dict):
                # Replies are matched to requests by order, so one stray line would shift every later reply
                # onto the wrong question: restart the helper instead.
                self._stop()
                raise RuntimeError(f"translation helper sent an unreadable reply: {line[:200]!r}")
            self._schedule_idle_stop()
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error", "translation failed"))
        return reply["texts"]

    def close(self) -> None:
        with self._lock:
            self._stop()

    def _start(self) -> None:
        if not Path(self._python).exists():
            raise RuntimeError(f"The translation environment is missing ({self._python}): "
                               f"run `faultsense setup-translation`")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", INDIC_DEVICE=self._device,
                   INDIC_BEAMS=str(self._beams))
        if self._token:
            env["HF_TOKEN"] = self._token
        self._process = subprocess.Popen(
            [self._python, self._worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._replies = queue.Queue()
        threading.Thread(target=_read_lines, args=(self._process, self._replies), daemon=True).start()

    def _stop(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    def _schedule_idle_stop(self) -> None:
        generation = self._generation
        self._timer = threading.Timer(self._idle, self._idle_stop, args=(generation,))
        self._timer.daemon = True
        self._timer.start()

    def _idle_stop(self, generation: int) -> None:
        with self._lock:
            if generation == self._generation:  # no request since this timer was set
                self._stop()


def _read_lines(process: subprocess.Popen, replies: queue.Queue) -> None:
    for line in process.stdout:
        replies.put(line)
    replies.put(None)  # the helper exited
