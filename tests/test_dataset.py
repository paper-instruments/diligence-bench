from __future__ import annotations

from datasets import Dataset
from diligence_bench import dataset as dataset_module
from diligence_bench.dataset import _flatten_rubric, load_diligence_bench


def test_flatten_rubric_preserves_criterion_schema() -> None:
    rubric = {
        "sections": [
            {
                "id": "thesis",
                "criteria": [
                    {
                        "id": "c1",
                        "weight": 1.5,
                        "requirement": "States the investment thesis.",
                    }
                ],
            },
            {
                "id": "risks",
                "criteria": [
                    {
                        "id": "c2",
                        "weight": -1.0,
                        "requirement": "Claims revenue is guaranteed.",
                    }
                ],
            },
        ]
    }

    assert _flatten_rubric(rubric) == [
        {
            "id": "c1",
            "section_id": "thesis",
            "weight": 1.5,
            "requirement": "States the investment thesis.",
        },
        {
            "id": "c2",
            "section_id": "risks",
            "weight": -1.0,
            "requirement": "Claims revenue is guaranteed.",
        },
    ]


def test_load_diligence_bench_uses_public_test_split(monkeypatch) -> None:
    calls = []
    raw = Dataset.from_list(
        [
            {
                "query": "Analyze ACME.",
                "datasetId": 42,
                "rubric": {
                    "sections": [
                        {
                            "id": "summary",
                            "criteria": [
                                {
                                    "id": "c1",
                                    "weight": 1.0,
                                    "requirement": "Mentions ACME.",
                                }
                            ],
                        }
                    ]
                },
            },
            {
                "query": "Analyze ZETA.",
                "datasetId": 43,
                "rubric": {"sections": []},
            },
        ]
    )

    def fake_load_dataset(dataset_id: str, *, split: str) -> Dataset:
        calls.append((dataset_id, split))
        return raw

    monkeypatch.setattr(dataset_module, "load_dataset", fake_load_dataset)

    loaded = load_diligence_bench(num_examples=1)

    assert calls == [(dataset_module.HF_DATASET_ID, dataset_module.HF_SPLIT)]
    assert loaded.column_names == ["prompt", "info"]
    assert len(loaded) == 1
    assert loaded[0] == {
        "prompt": [{"content": "Analyze ACME.", "role": "user"}],
        "info": {
            "datasetId": "42",
            "rubric": [
                {
                    "id": "c1",
                    "section_id": "summary",
                    "weight": 1.0,
                    "requirement": "Mentions ACME.",
                }
            ],
        },
    }
