from typer.testing import CliRunner

from faultsense.cli import app


def test_help_lists_fetch_manuals():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "fetch-manuals" in result.output


def test_extract_exits_1_when_the_report_has_problems(monkeypatch):
    from faultsense.ingest import extract as extract_mod
    from faultsense.ingest.faults import RejectedRow
    from faultsense.ingest.report import ManualReport

    def fake_extract(spec, manuals_dir):
        rejected = [RejectedRow(684, "heading-like line without a code-font code", "[Rotation Angle Monit]")]
        report = ManualReport(spec.id, fault_records=1, safety_chunks=1, rejected=rejected)
        return extract_mod.ExtractedManual(spec, "0" * 64, 10, [], [], [], report)

    monkeypatch.setattr(extract_mod, "extract_manual", fake_extract)
    monkeypatch.setattr(extract_mod, "save_extraction", lambda ex, out_dir: out_dir)
    monkeypatch.setattr(extract_mod, "write_report_file", lambda extracted, path: path)
    runner = CliRunner()
    failed = runner.invoke(app, ["extract", "--manual", "atv12"])
    assert failed.exit_code == 1
    assert "[Rotation Angle Monit]" in failed.output  # printed literally, not eaten as Rich markup
    assert runner.invoke(app, ["extract", "--manual", "atv12", "--accept-report"]).exit_code == 0


def test_db_init_without_database_url_prints_a_clear_error(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    result = CliRunner().invoke(app, ["db", "init"])
    assert result.exit_code == 2
    assert "DATABASE_URL" in result.output


def test_diagnose_prints_bracketed_names_and_json(monkeypatch):
    from faultsense import wiring
    from faultsense.diagnosis.schema import Cause, Citation, DiagnosisResponse, Meta

    citation = Citation(source_id="S1", manual="atv600", manual_title="ATV600", page=672)
    response = DiagnosisResponse(
        status="diagnosis", query="OCF", machine_id="DEMO-PUMP-01", language="en", matched_fault_codes=[],
        probable_causes=[Cause(rank=1, cause="Decrease [Current Limitation] CLI.", confidence=0.7,
                               fault_code="OCF", citations=[citation])],
        corrective_actions=[], safety_warnings=[], escalation=None, sources=[],
        meta=Meta(retrieval_top_score=1.0, llm_called=True),
    )

    class FakeService:
        def diagnose(self, query, machine_id=None):
            return response

    monkeypatch.setattr(wiring, "build_service", lambda components=None: FakeService())
    runner = CliRunner()
    plain = runner.invoke(app, ["diagnose", "OCF", "--machine", "DEMO-PUMP-01"])
    assert plain.exit_code == 0 and "[Current Limitation]" in plain.output
    as_json = runner.invoke(app, ["diagnose", "OCF", "--json"])
    assert as_json.exit_code == 0 and '"status": "diagnosis"' in as_json.output


def test_translate_command_shows_the_shielded_translation(monkeypatch):
    from faultsense import wiring
    from faultsense.translation import FakeTranslator

    monkeypatch.setattr(wiring, "build_translator", lambda settings=None: FakeTranslator())
    result = CliRunner().invoke(app, ["translate", "Check OHF for 15 minutes.", "--to", "ta"])
    assert result.exit_code == 0 and "ta: Check OHF for 15 minutes." in result.output
    monkeypatch.setattr(wiring, "build_translator", lambda settings=None: None)
    assert CliRunner().invoke(app, ["translate", "x"]).exit_code == 1


def test_setup_translation_installs_the_environment_then_warms_up(monkeypatch):
    import subprocess

    from faultsense import wiring
    from faultsense.translation import FakeTranslator

    ran = []
    monkeypatch.setattr(subprocess, "run", lambda command, check: ran.append([str(part) for part in command]))
    translator = FakeTranslator()
    translator.close = lambda: None
    monkeypatch.setattr(wiring, "build_translator", lambda settings=None: translator)
    result = CliRunner().invoke(app, ["setup-translation"])
    assert result.exit_code == 0 and "Ready" in result.output
    installs = [" ".join(command) for command in ran]
    assert any("transformers==4.57.6" in c and "indictranstoolkit==1.1.1" in c for c in installs)
    assert any("download.pytorch.org/whl/cpu" in c for c in installs)
    assert [(source, target) for _, source, target in translator.calls] == [("en", "hi"), ("ta", "en")]
