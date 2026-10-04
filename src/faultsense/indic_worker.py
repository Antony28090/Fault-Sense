"""Translation helper for FaultSense: runs IndicTrans2 in the separate `.venv-indic` environment.

IndicTrans2's model code needs transformers 4 and IndicTransToolkit, while FaultSense needs transformers
5, so this file runs under `.venv-indic`'s Python and never imports faultsense. It answers one JSON line per
request on stdin: {"texts": [...], "source": "en", "target": "hi"} -> {"ok": true, "texts": [...]} or
{"ok": false, "error": "..."}. Models load on first use, on the CPU unless INDIC_DEVICE says otherwise;
INDIC_BEAMS sets the beam count (default 1, greedy: about 2.5x faster than 5 beams for the same check pass rate).
"""
from __future__ import annotations

import json
import os
import sys

TAGS = {"en": "eng_Latn", "hi": "hin_Deva", "ta": "tam_Taml"}
MODELS = {"to_indic": "ai4bharat/indictrans2-en-indic-dist-200M",
          "to_english": "ai4bharat/indictrans2-indic-en-dist-200M"}
_loaded: dict[str, tuple] = {}
_processor = None


def _load(direction: str) -> tuple:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    token = os.environ.get("HF_TOKEN") or None
    device = os.environ.get("INDIC_DEVICE", "cpu")
    tokenizer = AutoTokenizer.from_pretrained(MODELS[direction], trust_remote_code=True, token=token)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODELS[direction], trust_remote_code=True, token=token).to(device)
    if device != "cpu":
        model = model.half()
    return tokenizer, model.eval(), device


def translate(texts: list[str], source: str, target: str, batch_size: int = 8) -> list[str]:
    global _processor
    import torch
    from IndicTransToolkit import IndicProcessor

    if _processor is None:
        _processor = IndicProcessor(inference=True)
    direction = "to_english" if target == "en" else "to_indic"
    if direction not in _loaded:
        _loaded[direction] = _load(direction)
    tokenizer, model, device = _loaded[direction]
    out: list[str] = []
    for start in range(0, len(texts), batch_size):
        batch = _processor.preprocess_batch(texts[start:start + batch_size], src_lang=TAGS[source], tgt_lang=TAGS[target])
        inputs = tokenizer(batch, truncation=True, padding="longest", return_tensors="pt",
                           return_attention_mask=True).to(device)
        with torch.inference_mode():
            # use_cache=False: the models' own decoder code predates transformers 4.5x's cache objects.
            generated = model.generate(**inputs, use_cache=False, min_length=0, max_length=256,
                                       num_beams=int(os.environ.get("INDIC_BEAMS", "1")), num_return_sequences=1)
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=True)
        out += _processor.postprocess_batch(decoded, lang=TAGS[target])
    return out


def serve(lines, write, translate_fn=translate) -> None:
    for line in lines:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            reply = {"ok": True, "texts": translate_fn(request["texts"], request["source"], request["target"])}
        except Exception as exc:  # reported to FaultSense, which then shows English
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        write(json.dumps(reply, ensure_ascii=False) + "\n")


def main(translate_fn=translate) -> None:
    # Replies go to a private copy of stdout. Anything else written to stdout, by Python or by native library
    # code, is sent to stderr, so it cannot break the one-line-per-reply protocol.
    sys.stdout.flush()
    replies = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", newline="\n")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr

    def write(text: str) -> None:
        replies.write(text)
        replies.flush()

    serve(sys.stdin, write, translate_fn)


if __name__ == "__main__":
    main()
