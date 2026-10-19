"""Development-only Pilot-120 regression test for candidate-choice rules.

No gold / route is available to the predictor. The scorer opens it only
AFTER the source-only inference pass and never mutates frozen inputs.
On a detached prototype release without the parent research checkout,
this test skips. CI on the complete parent repository exercises all 120.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from run_pilot120_diagnostic_v03 import evaluate

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[4]
SOURCE = REPO_ROOT / 'data/annotations/pilot_120_v1/source_canonical.jsonl'
BASELINE = REPO_ROOT / 'research/pilot120/gliner25_action_readiness_repair_v1/baseline83.predictions.jsonl'


class FrozenDevelopmentPanelTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE.is_file() and BASELINE.is_file(),
                         'Requires the whole research repository / frozen Pilot-120')
    def test_contextual_probe_over_all_120(self):
        with tempfile.TemporaryDirectory(prefix='compound_v03_') as temp:
            result = evaluate(REPO_ROOT, Path(temp))
            assert result['n'] == 120
            assert result['source_only_99_total'] == 99
            assert result['baseline_83_correct'] == 83
            # Inference is explicitly source-only; all metrics are exploratory.
            # Do not assert a research improvement as if it were a held-out test.
            print('\nV03_PILOT120_DEVELOPMENT_METRICS=' + json.dumps({
                'source_only_99_correct': result['source_only_99_correct'],
                'hybrid_correct': result['hybrid_correct'],
                'confusion': result['confusion'],
                'wrong_ids': result['wrong_ids'],
                'unresolved_n': result['unresolved_n'],
            }, sort_keys=True), flush=True)


if __name__ == '__main__':
    unittest.main()