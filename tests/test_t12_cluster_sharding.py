"""CPU tests for T12 deterministic shard planning."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.sharding import (
    ShardPlanningError,
    plan_shards_from_jsonl,
    plan_to_canonical_json,
)


class T12ClusterShardingTests(unittest.TestCase):
    def _write_jsonl(self, directory: Path, records: list[dict]) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "input.jsonl"
        lines = [json.dumps(record, sort_keys=True) for record in records]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_repeated_planning_is_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [{"fixture_id": f"syn-{index:03d}", "value": index} for index in range(1, 11)]
            path = self._write_jsonl(root, records)
            first = plan_to_canonical_json(
                plan_shards_from_jsonl(
                    path,
                    id_field="fixture_id",
                    shard_count=3,
                    created_timestamp="2026-07-11T18:00:00Z",
                )
            )
            second = plan_to_canonical_json(
                plan_shards_from_jsonl(
                    path,
                    id_field="fixture_id",
                    shard_count=3,
                    created_timestamp="2026-07-11T18:00:00Z",
                )
            )
            self.assertEqual(first, second)

    def test_duplicate_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write_jsonl(
                root,
                [
                    {"fixture_id": "a", "value": 1},
                    {"fixture_id": "a", "value": 2},
                ],
            )
            with self.assertRaises(ShardPlanningError):
                plan_shards_from_jsonl(
                    path,
                    id_field="fixture_id",
                    shard_count=1,
                    created_timestamp="2026-07-11T18:00:00Z",
                )

    def test_zero_shard_count_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write_jsonl(root, [{"fixture_id": "a"}])
            with self.assertRaises(ShardPlanningError):
                plan_shards_from_jsonl(
                    path,
                    id_field="fixture_id",
                    shard_count=0,
                    created_timestamp="2026-07-11T18:00:00Z",
                )

    def test_shard_counts_differ_by_at_most_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [{"fixture_id": f"id-{index}", "value": index} for index in range(10)]
            path = self._write_jsonl(root, records)
            plan = plan_shards_from_jsonl(
                path,
                id_field="fixture_id",
                shard_count=4,
                created_timestamp="2026-07-11T18:00:00Z",
            )
            counts = list(plan.shard_record_counts)
            self.assertEqual(sum(counts), 10)
            self.assertLessEqual(max(counts) - min(counts), 1)

    def test_original_ordinal_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [{"fixture_id": f"id-{index}", "value": index} for index in range(5)]
            path = self._write_jsonl(root, records)
            plan = plan_shards_from_jsonl(
                path,
                id_field="fixture_id",
                shard_count=2,
                created_timestamp="2026-07-11T18:00:00Z",
            )
            flattened = [record_id for shard in plan.shard_record_ids for record_id in shard]
            self.assertEqual(flattened, [f"id-{index}" for index in range(5)])

    def test_input_mutation_changes_plan_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path_a = self._write_jsonl(root, [{"fixture_id": "a", "value": 1}])
            path_b = self._write_jsonl(root / "b", [{"fixture_id": "a", "value": 2}])
            plan_a = plan_shards_from_jsonl(
                path_a,
                id_field="fixture_id",
                shard_count=1,
                created_timestamp="2026-07-11T18:00:00Z",
            )
            plan_b = plan_shards_from_jsonl(
                path_b,
                id_field="fixture_id",
                shard_count=1,
                created_timestamp="2026-07-11T18:00:00Z",
            )
            self.assertNotEqual(plan_a.input_sha256, plan_b.input_sha256)

    def test_no_python_randomised_hash(self) -> None:
        sharding_source = (
            Path(__file__).resolve().parents[1] / "src/ambiguity_manager/model/cluster/sharding.py"
        ).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?<![\w])hash\s*\(", sharding_source))


if __name__ == "__main__":
    unittest.main()
