from __future__ import annotations

import json
import tomllib

from diligence_bench.harbor import DiligenceBenchAdapter, load_tasks_from_dir


def test_adapter_writes_harbor_task_dir(tmp_path, monkeypatch):
    rows = [
        {
            "prompt": [{"role": "user", "content": "Assess liquidity."}],
            "info": {
                "datasetId": "sample_1",
                "rubric": [
                    {
                        "id": "c1",
                        "section_id": "thesis",
                        "weight": 1,
                        "requirement": "States a thesis",
                    }
                ],
            },
        }
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)

    generated = DiligenceBenchAdapter(out_dir=tmp_path, num_examples=1).generate()

    assert len(generated) == 1
    task_dir = generated[0]
    assert (task_dir / "instruction.md").exists()
    assert (task_dir / "task.toml").exists()
    assert (task_dir / "environment" / "Dockerfile").exists()
    assert (
        task_dir / "environment" / "diligence_bench" / "tools" / "sec_edgar" / "server.py"
    ).exists()
    assert (
        task_dir / "environment" / "diligence_bench" / "tools" / "web_search" / "server.py"
    ).exists()
    assert (task_dir / "tests" / "test.sh").exists()
    rubric = json.loads((task_dir / "tests" / "rubric.json").read_text(encoding="utf-8"))
    assert rubric[0]["id"] == "c1"
    assert "/workspace/answer.md" in (task_dir / "instruction.md").read_text(encoding="utf-8")
    task_toml = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    assert task_toml["verifier"]["env"]["MODEL_NAME"].startswith("openrouter/")
    assert task_toml["agent"]["env"]["DILIGENCE_BENCH_WEB_FETCH_WRITE"] == "1"


def test_loader_round_trips_generated_task(tmp_path, monkeypatch):
    rows = [
        {
            "prompt": [{"role": "user", "content": "Assess refinancing risk."}],
            "info": {
                "datasetId": "sample_2",
                "rubric": [
                    {
                        "id": "c1",
                        "section_id": "risk",
                        "weight": 2,
                        "requirement": "Ranks refinancing risk",
                    }
                ],
            },
        }
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)
    DiligenceBenchAdapter(out_dir=tmp_path).generate()

    tasks = load_tasks_from_dir(tmp_path)

    assert len(tasks) == 1
    assert tasks[0]["info"]["datasetId"] == "sample_2"
    assert tasks[0]["info"]["rubric"][0]["section_id"] == "risk"
    assert "Assess refinancing risk." in tasks[0]["prompt"][0]["content"]


def test_adapter_clears_stale_generated_task_dirs(tmp_path, monkeypatch):
    rows = [
        {
            "prompt": [{"role": "user", "content": "Assess liquidity."}],
            "info": {"datasetId": "sample_1", "rubric": []},
        },
        {
            "prompt": [{"role": "user", "content": "Assess leverage."}],
            "info": {"datasetId": "sample_2", "rubric": []},
        },
    ]
    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows)
    DiligenceBenchAdapter(out_dir=tmp_path).generate()
    assert len(list(tmp_path.glob("dilbench-*"))) == 2

    monkeypatch.setattr("diligence_bench.harbor.adapter.load_diligence_bench", lambda **_: rows[:1])
    DiligenceBenchAdapter(out_dir=tmp_path).generate()

    assert len(list(tmp_path.glob("dilbench-*"))) == 1
