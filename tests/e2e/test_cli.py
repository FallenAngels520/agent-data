import json
from pathlib import Path

from typer.testing import CliRunner

from agent_data import cli
from agent_data.application.process_document import ProcessResult

runner = CliRunner()


class FakeProcessor:
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None]] = []

    def run(self, value: str, *, task_context: str | None = None) -> ProcessResult:
        self.calls.append((value, task_context))
        return self.result


def test_cli_help_lists_process_command() -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "process" in result.stdout


def test_cli_process_prints_output_and_returns_quality_exit_code(
    monkeypatch, tmp_path: Path
) -> None:
    output = tmp_path / "output" / "doc"
    fake = FakeProcessor(
        ProcessResult(
            status="rejected",
            exit_code=2,
            document_id="doc_test",
            output_dir=output,
            package=None,
        )
    )
    monkeypatch.setattr(cli, "build_processor", lambda **kwargs: fake)

    result = runner.invoke(
        cli.app,
        ["process", "sample.pdf", "--output", str(tmp_path), "--task-context", "growth"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "rejected"
    assert payload["output"] == str(output)
    assert fake.calls == [("sample.pdf", "growth")]


def test_cli_invalid_configuration_uses_exit_code_3(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    result = runner.invoke(cli.app, ["process", "sample.pdf", "--output", str(tmp_path)])
    assert result.exit_code == 3
    assert "LLM_API_KEY" in result.stdout


def test_cli_rejects_disabling_required_raw_retention(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["process", "sample.pdf", "--output", str(tmp_path), "--no-keep-raw"],
    )
    assert result.exit_code == 3
    assert "raw retention" in result.stdout.lower()
