from __future__ import annotations

import json
from io import StringIO

from diligence_bench.summary import print_summary


def test_summary_prints_harness_column(tmp_path) -> None:
    score_dir = tmp_path / "run" / "finance__openai_gpt-5" / "scores"
    score_dir.mkdir(parents=True)
    (score_dir / "sample.json").write_text(
        json.dumps(
            {
                "model": "finance__openai_gpt-5",
                "harness": "vf-harness",
                "score": 1.0,
                "num_turns": 4,
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    stream = StringIO()

    print_summary(tmp_path / "run", stream=stream)

    output = stream.getvalue()
    assert output.startswith("harness model completed")
    assert "vf-harness finance__openai_gpt-5" in output
