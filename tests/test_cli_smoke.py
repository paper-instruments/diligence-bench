from __future__ import annotations

from pathlib import Path

from diligence_bench.results import EvalResult


def test_list_agents_prints_finance(capsys):
    from diligence_bench.cli import main

    main(["list-agents"])

    assert "finance" in capsys.readouterr().out


def test_build_tasks_command_invokes_adapter(monkeypatch, tmp_path):
    from diligence_bench.cli import main

    calls = {}

    class FakeAdapter:
        def __init__(self, out_dir, num_examples, verifier_model):
            calls["init"] = (Path(out_dir), num_examples, verifier_model)

        def generate(self):
            calls["generated"] = True

    monkeypatch.setattr("diligence_bench.cli.DiligenceBenchAdapter", FakeAdapter)

    main(["build-tasks", "--out", str(tmp_path), "--examples", "2"])

    assert calls["init"][0] == tmp_path
    assert calls["init"][1] == 2
    assert calls["generated"] is True


def test_eval_command_writes_ablation_with_stubbed_runner(monkeypatch, tmp_path):
    from diligence_bench.cli import main

    async def fake_run_eval(**kwargs):
        run_dir = Path(kwargs["output_dir"]) / kwargs["run_id"] / "finance__openai_gpt-5" / "scores"
        run_dir.mkdir(parents=True, exist_ok=True)
        return [
            EvalResult(
                run_id=kwargs["run_id"],
                model="finance__openai_gpt-5",
                dataset_id="sample",
                query="Question",
                answer="Answer",
                score=1.0,
                section_scores={"thesis": 1.0},
                verdicts=[],
                num_turns=1,
                judge_model=kwargs["judge_model"],
                underlying_model=kwargs["model"],
                harness="vf-harness",
            )
        ]

    monkeypatch.setattr("diligence_bench.cli.run_eval", fake_run_eval)
    monkeypatch.setattr(
        "diligence_bench.cli._judge_client",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr("diligence_bench.cli.print_summary", lambda *_, **__: None)

    main(
        [
            "eval",
            "--models",
            "openai/gpt-5",
            "--tasks-dir",
            str(tmp_path / "tasks"),
            "--output",
            str(tmp_path / "results"),
            "--run-id",
            "run",
        ]
    )

    assert (tmp_path / "results" / "ablations.csv").exists()


def test_eval_command_rejects_zero_concurrency(capsys):
    from diligence_bench.cli import main

    try:
        main(["eval", "--models", "openai/gpt-5", "--concurrency", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse to reject zero concurrency")

    assert "must be at least 1" in capsys.readouterr().err
