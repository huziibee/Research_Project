from __future__ import annotations

from pathlib import Path

from scripts.pilot120_early_analysis import _cost, _load_policy, _two_sided_sign_pvalue


ROOT = Path(__file__).resolve().parents[1]


def test_early_policy_is_explicitly_non_official_and_non_tuning() -> None:
    policy = _load_policy(ROOT / "configs/evaluation/pilot120_early_analysis_policy_v1.json")
    assert policy["valid_for_official_use"] is False
    assert policy["must_not_influence_training_selection_or_tuning"] is True
    assert _cost(policy, "face_preserving_rejection", "execute") > _cost(
        policy, "execute", "clarify"
    )


def test_paired_sign_test_is_exact_and_symmetric() -> None:
    assert _two_sided_sign_pvalue(0, 0) == 1.0
    assert _two_sided_sign_pvalue(3, 1) == _two_sided_sign_pvalue(1, 3)
    assert _two_sided_sign_pvalue(10, 0) < 0.01
