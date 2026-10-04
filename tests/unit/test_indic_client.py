"""The IndicTrans2 helper client, against a stand-in worker script in a real subprocess (no models)."""
import sys
import textwrap
import threading
import time

import pytest

from faultsense.translation import IndicTrans2Translator

FAKE_WORKER = textwrap.dedent('''
    import json, sys, time
    for line in sys.stdin:
        request = json.loads(line)
        texts = request["texts"]
        if "CRASH" in texts:
            sys.exit(3)
        if "SLOW" in texts:
            time.sleep(5)
        if "NOISE" in texts:
            sys.stdout.write("a library printed this\\n")
        if "BEAMS" in texts:
            texts = [__import__("os").environ.get("INDIC_BEAMS", "unset")]
        if "ERROR" in texts:
            reply = {"ok": False, "error": "model files missing"}
        else:
            reply = {"ok": True, "texts": [f"{request['target']}: {t}" for t in texts]}
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\\n")
        sys.stdout.flush()
''')


@pytest.fixture
def make(tmp_path):
    worker = tmp_path / "fake_worker.py"
    worker.write_text(FAKE_WORKER, encoding="utf-8")
    made = []

    def build(**kwargs):
        translator = IndicTrans2Translator(python=sys.executable, worker=worker, **kwargs)
        made.append(translator)
        return translator

    yield build
    for translator in made:
        translator.close()


def test_the_helper_starts_on_first_use_and_translates(make):
    translator = make()
    assert translator._process is None
    assert translator.translate(["नमस्ते", "OHF"], "en", "ta") == ["ta: नमस्ते", "ta: OHF"]
    assert translator.translate(["same"], "hi", "hi") == ["same"]  # nothing to translate, no request
    first = translator._process.pid
    translator.translate(["again"], "en", "hi")
    assert translator._process.pid == first  # reused, not restarted


def test_an_error_reply_raises(make):
    with pytest.raises(RuntimeError, match="model files missing"):
        make().translate(["ERROR"], "en", "hi")


def test_a_crashed_helper_raises_and_is_restarted_next_time(make):
    translator = make()
    with pytest.raises(RuntimeError, match="stopped"):
        translator.translate(["CRASH"], "en", "hi")
    assert translator.translate(["ok"], "en", "hi") == ["hi: ok"]


def test_a_hung_helper_is_killed_after_the_timeout(make):
    translator = make(timeout=1)
    with pytest.raises(RuntimeError, match="timed out"):
        translator.translate(["SLOW"], "en", "hi")
    assert translator._process is None


def test_the_helper_stops_after_the_idle_time(make):
    translator = make(idle_minutes=0.5 / 60)  # half a second
    translator.translate(["ok"], "en", "hi")
    process = translator._process
    time.sleep(1.5)
    assert translator._process is None and process.poll() is not None
    assert translator.translate(["back"], "en", "ta") == ["ta: back"]


def test_concurrent_requests_are_answered_one_at_a_time(make):
    translator = make()
    results = {}

    def ask(word):
        results[word] = translator.translate([word], "en", "hi")

    threads = [threading.Thread(target=ask, args=(word,)) for word in ("one", "two", "three")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == {"one": ["hi: one"], "two": ["hi: two"], "three": ["hi: three"]}


def test_a_missing_environment_is_explained(tmp_path):
    translator = IndicTrans2Translator(python=tmp_path / "nope" / "python.exe")
    with pytest.raises(RuntimeError, match="setup-translation"):
        translator.translate(["x"], "en", "hi")


def test_the_worker_loop_answers_each_line_and_reports_errors():
    from faultsense.indic_worker import serve

    written = []

    def fake_translate(texts, source, target):
        if texts == ["boom"]:
            raise OSError("no weights")
        return [t.upper() for t in texts]

    serve(['{"texts": ["a"], "source": "en", "target": "hi"}\n', "\n",
           '{"texts": ["boom"], "source": "en", "target": "hi"}\n'], written.append, fake_translate)
    assert [line.strip() for line in written] == [
        '{"ok": true, "texts": ["A"]}', '{"ok": false, "error": "OSError: no weights"}']


def test_the_beam_count_reaches_the_helper(make):
    assert make().translate(["BEAMS"], "en", "hi") == ["hi: 1"]  # greedy by default: 2.5x faster, same check pass rate
    assert make(beams=5).translate(["BEAMS"], "en", "hi") == ["hi: 5"]


def test_an_unreadable_reply_restarts_the_helper_so_replies_stay_in_step(make):
    translator = make()
    with pytest.raises(RuntimeError, match="unreadable"):
        translator.translate(["NOISE"], "en", "hi")
    assert translator.translate(["next"], "en", "hi") == ["hi: next"]  # not the reply meant for NOISE


def test_the_worker_keeps_library_output_off_the_reply_stream(tmp_path):
    import json
    import subprocess

    script = tmp_path / "noisy.py"
    script.write_text(textwrap.dedent('''
        import os
        from faultsense import indic_worker

        def noisy(texts, source, target):
            os.write(1, b"native library noise\\n")
            print("python library noise")
            return [t.upper() for t in texts]

        indic_worker.main(noisy)
    '''), encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], input='{"texts": ["ok"], "source": "en", "target": "hi"}\n',
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert [json.loads(line) for line in done.stdout.splitlines()] == [{"ok": True, "texts": ["OK"]}]
