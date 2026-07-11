"""Tests for prediction-only JSON schema export."""

from __future__ import annotations

import json
import unittest

from ambiguity_manager.schema.v2.json_schema import (
    build_canonical_record_v2_json_schema,
    build_prediction_json_schema,
    canonical_record_v2_json_schema_bytes,
    prediction_json_schema_bytes,
)
from ambiguity_manager.schema.v2.taxonomies import RecordClass
from ambiguity_manager.schema.v2.version import SCHEMA_VERSION


class T12PredictionSchemaTests(unittest.TestCase):
    def test_no_gold_source_branch(self) -> None:
        schema = build_prediction_json_schema()
        self.assertNotIn("oneOf", schema)
        self.assertEqual(
            schema["properties"]["record_class"]["const"],
            RecordClass.PREDICTION.value,
        )

    def test_full_canonical_still_has_oneof(self) -> None:
        full = build_canonical_record_v2_json_schema()
        self.assertIn("oneOf", full)
        self.assertEqual(len(full["oneOf"]), 2)

    def test_deterministic_bytes(self) -> None:
        first = prediction_json_schema_bytes()
        second = prediction_json_schema_bytes()
        self.assertEqual(first, second)
        parsed = json.loads(first.decode("utf-8"))
        self.assertEqual(parsed["schema_version"], SCHEMA_VERSION)

    def test_prediction_metadata_required(self) -> None:
        schema = build_prediction_json_schema()
        self.assertIn("prediction_metadata", schema["required"])

    def test_gold_record_class_not_allowed(self) -> None:
        schema = build_prediction_json_schema()
        record_class = schema["properties"]["record_class"]
        self.assertEqual(record_class["const"], "prediction")
        self.assertNotIn("enum", record_class)

    def test_full_schema_bytes_unchanged(self) -> None:
        self.assertEqual(
            canonical_record_v2_json_schema_bytes(),
            canonical_record_v2_json_schema_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
