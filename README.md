# FaultSense

Diagnostic assistant for Schneider Electric Altivar variable-speed drives. Phase 1: English text in, ranked causes + step-by-step fixes out, every item cited to a manual page.

## Setup (Windows, Git Bash)

1. Python 3.11+ virtual environment with CUDA PyTorch:
   ```bash
   py -3.13 -m venv .venv
   source .venv/Scripts/activate
   python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
   python -m pip install -e ".[dev]"
   ```
2. Manuals (about 54 MB from Schneider Electric's download server):
   ```bash
   faultsense fetch-manuals
   ```
3. Configuration: `cp .env.example .env`, then fill in `DATABASE_URL` and the LLM key (see below).

## Supabase setup

1. Create a free project at supabase.com (region: Mumbai / `ap-south-1`).
2. Project -> **Connect** -> **Session pooler**: copy the URI into `.env` as `DATABASE_URL` and put your database password in it. The direct connection host is IPv6-only, so use the pooler.
3. `faultsense db init` creates the `vector` extension, tables and indexes.

## LLM

Set `LLM_API_KEY` (or `ANTHROPIC_API_KEY`) in `.env`. The default model is `claude-opus-5-5`; change it with `LLM_MODEL`.

### Local open-weight models (Ollama)

Install [Ollama](https://ollama.com), pull a model, and point FaultSense at it. Nothing leaves the machine except the database queries, and there is no per-call cost.

```bash
ollama pull qwen3.5:4b
LLM_PROVIDER=ollama LLM_MODEL=qwen3.5:4b faultsense diagnose "OHF on the pump" --machine DEMO-PUMP-01
```

Put `LLM_PROVIDER=ollama` and `LLM_MODEL=...` in `.env` to make it the default. `OLLAMA_URL`, `OLLAMA_NUM_CTX` (default 16384; prompts carry 8+ manual passages) and `OLLAMA_THINK` (default off) tune it. Compare a local model with Claude by running `faultsense eval run` with each and then `faultsense eval compare`.

Measured on the 40 eval scenarios (provisional until they are reviewed): Claude rewrite + local `qwen3.5:4b` diagnosis matched all-Claude on every quality metric, at about 15 s per answer on an 8 GB laptop GPU.

Small local models write weaker search rewrites for symptom questions, which costs retrieval accuracy. `REWRITE_PROVIDER` and `REWRITE_MODEL` move just that short call to another model, for example Claude for the rewrite (about 0.1 cent per symptom question) and a free local model for the diagnosis:

```bash
LLM_PROVIDER=ollama LLM_MODEL=qwen3.5:4b REWRITE_PROVIDER=anthropic REWRITE_MODEL=claude-sonnet-5-5 faultsense eval run
```

## Running

```bash
faultsense extract                      # parse PDFs, print the extraction report
faultsense ingest                       # extract + embed + store in Supabase
faultsense search "drive trips on hot afternoons" --machine DEMO-PUMP-01
faultsense diagnose "OHF on the pump" --machine DEMO-PUMP-01
faultsense serve                        # operator page at http://127.0.0.1:8000/
```

### Operator page

`faultsense serve`, then open http://127.0.0.1:8000/ on the same computer. Pick the machine tile, type (or speak) the code on the drive's display or describe the problem, and press Diagnose (or Ctrl+Enter).

- While it works, live progress shows each real step: the code it recognised and the manual page it found, then writing and checking the answer.
- The answer opens with the fault code drawn like the drive's 7-segment display, then any safety warnings, the likely causes and a tick-off checklist of steps ("3 of 6 done").
- Tap any page tag to read that exact manual passage in a side panel, with a button that opens the PDF at the page.
- Copy answer and Copy report put a plain-text summary on the clipboard for a message or log book.
- When the manuals do not support an answer it says to call a maintenance engineer, with a checklist and a copyable summary.
- Light, dark or automatic theme from the button in the top bar. The microphone appears only in browsers with speech recognition (Chrome, Edge), which send the audio to the browser maker's speech service.

To use it from a phone on the same Wi-Fi, run `faultsense serve --host 0.0.0.0` and open `http://<this computer's IP>:8000/`. There is no login, so only do this on a network you trust.

### Hindi and Tamil

The language switch in the top bar (English · हिन्दी · தமிழ்) changes the page, the microphone language and the answer language. Questions typed or spoken in Hindi or Tamil are translated to English, diagnosed exactly as English questions are, and the checked English answer is translated back. "Show English" switches to the original, and the DANGER panel always shows both languages. Fault codes, parameter names, numbers and page references are protected during translation: a sentence that would lose one is shown in English instead.

Translation runs locally with AI4Bharat's IndicTrans2 (IIT Madras, MIT licence). Its model code needs an older transformers version than FaultSense, so it runs in its own environment, `.venv-indic`, as a helper that starts on the first Hindi or Tamil question and stops after 15 minutes without one (`TRANSLATION_IDLE_MINUTES`) or when FaultSense stops; English-only use never starts it. While running it uses about 1.2 GB of RAM; the environment and models take about 3 GB of disk.

One-time setup:

1. The models are gated on Hugging Face: accept the terms on [indictrans2-en-indic-dist-200M](https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M) and [indictrans2-indic-en-dist-200M](https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M), then put a read token in `.env` as `HF_TOKEN`.
2. Run `faultsense setup-translation` (builds `.venv-indic`, downloads the models and translates two test sentences).

Check it any time with `faultsense translate "Wait 15 minutes." --to ta`. `TRANSLATION=off` answers in English only. The page's Hindi and Tamil wording and the Hindi/Tamil test questions were written by Claude and need a native speaker's check.

### HTTP API

```bash
faultsense serve
curl -s -X POST http://127.0.0.1:8000/diagnose -H "Content-Type: application/json" -d '{"query": "Pump drive trips on hot afternoons", "machine_id": "DEMO-PUMP-01"}'
```

The response lists `probable_causes`, `corrective_actions` and `safety_warnings`, each with `citations` (manual + page), or `status: "escalate"` with an escalation summary when the manuals do not support an answer. `GET /health` reports the manuals, machines and database status (503 when diagnoses would fail). `GET /info` lists the machines and the models in use, `GET /manuals/<id>.pdf` serves a downloaded manual, `GET /passages/<chunk id>` returns the manual text behind a citation, and `POST /diagnose/stream` returns the same diagnosis as newline-delimited JSON: stage events while it works, then the result.

## Evaluation

```bash
faultsense eval run --retrieval-only    # retrieval metrics only; skips the diagnosis LLM (query rewriting still makes one small call per symptom query)
faultsense eval run                     # full pipeline
faultsense eval compare eval_runs/<run A> eval_runs/<run B>
```

Four scenario sets, all `reviewed: false` until a person checks them:

- `data/eval/scenarios.yaml`: 40 drafts written from the manuals.
- `data/eval/scenarios_indic.yaml`: 16 Hindi and Tamil questions adapted from the real-world set; the scorecard adds "Translation shown in English", the share of translated sentences that fell back to English.
- `data/eval/scenarios_operator.yaml`: 25 questions in shop-floor wording: typos, codes misread off the display (0HF) or typed with a space (SCF 1), romanised Hindi and Tamil, symptoms with no code, a drive model named instead of a machine, and three questions that should be refused.
- `data/eval/scenarios_web.yaml`: 57 real customer questions from Schneider Electric's public FAQ pages, each with its `source_url` and Schneider's answer paraphrased in `reference_answer`. Run it with `faultsense eval run --scenarios data/eval/scenarios_web.yaml`.

Measured 2026-10-04 (Claude rewrite + local `qwen3.5:4b`): on the real-world set, correct cause in top 3 96.2% (51 of 53), fault code detected 100%, hit@5 96.2%, hallucination in the final answer 0%, 4 of 4 questions about products without a manual refused, false escalation 1.9%, answer time 15 s typical / 24 s slow. Operator wording: correct cause 95.2% (20 of 21), no false escalations, 3 of 3 refused. Hindi and Tamil: correct cause 92.9% (13 of 14), hit@5 100%, 2.0% of translated sentences shown in English, 24 s typical. The weakest area is a drive that is not running but shows no fault (rdY, a zero speed display): the manual explains these in setup chapters that rank below fault pages.

### Tuning

- `EVIDENCE_THRESHOLD` (0.14): a question with no recognised fault code is escalated without calling the LLM when the best manual passage scores below it. It is set 0.05 below the lowest score of any in-scope test question without a code; out-of-scope questions that still pass rely on the LLM answering "insufficient evidence".
- `CAUSE_MATCH_THRESHOLD` (0.65): how close (bge-m3 cosine) an answer's cause must be to an expected cause to count as "correct cause in top 3". Check the borderline `cause_pairs` in `eval_runs/*/results.jsonl` before changing it; a different cause of the same fault can score above it.
- Query rewriting is non-deterministic, so scores move a little between runs: compare runs with `faultsense eval compare` rather than single numbers.
- Scores stay provisional until scenarios are `reviewed: true`.

## Tests

```bash
pytest                 # unit tests
pytest -m manuals      # golden tests on the real PDFs
pytest -m db           # Supabase integration (uses a throwaway schema)
pytest -m models       # real embedding / reranker weights
```
