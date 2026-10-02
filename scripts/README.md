# Scripts

The reusable package is under `src/ambiguity_manager/`. The scripts here are
entry points for versioned data preparation, evaluation, scoring, and audits.

| Task | Main scripts |
| --- | --- |
| Pilot-120 generation and routing | `evaluate_pilot_120_direct_base.py`, `evaluate_pilot_120_manager_systems.py`, `evaluate_goal_first_manager_v2.py` |
| T0.7 intent and scoring | `evaluate_pilot_120_intent_box.py`, `build_intent_box_sgc_packet_20260913.py`, `build_t07_manager_sgc_packet_20260922.py`, `semantic_intent/run_blind_semantic_judge.py`, `score_t07_matched_baseline_20260922.py` |
| One-turn recovery | `one_turn_recovery_20260922.py` |
| Frozen Goal-First semantics to GLiNER routes | [`experiments/gliner25_goalfirst_semantic_router_v1.py`](experiments/gliner25_goalfirst_semantic_router_v1.py): locked protocol, seven inference conditions, saved-result scoring |
| ABLE IX scoring | `score_gf_temp_ablation_20260923.py`, `aggregate_able_ix_means_20260923.py` |
| Dataset converters | `convert_*.py`; source acquisition and pins are in `docs/DATASETS.md` |
| Repository and case checks | `release/check_repository.py`, `release/build_pilot120_cases.py` |

Scripts with `t12_`, `t27`, `t28`, `pilot120_t39`, and similar ticket names
preserve historical experiment contracts. They are not automatically current
launchers. Use `python scripts/<name>.py --help` and the linked versioned
protocol before a new run. Project-owned writes should go through
`ambiguity_manager.io_guard.resolve_writable_path` to protect `data/raw/`.
