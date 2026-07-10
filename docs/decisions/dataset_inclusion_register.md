# Dataset Inclusion Register

Register schema: `1.0.0`
Updated at (curated): `2026-07-10T00:00:00Z`

Computed payload verification and row counts come from the latest audit JSON.

| Dataset | Decision | Role | Payload | Mapping | Total rows | Components | Converter |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ambik | include | core | verified | TODO_VERIFY | 1000 | primary=1000 | T03 |
| indirect_requests | include | core | verified | TODO_VERIFY | 906 | test=388, train=246, validation=272 | T04 |
| clara | conditional | conditional_core | verified | TODO_VERIFY | 5345 | agument.json=5345 | T07 |
| codraw_icr_v2 | conditional | conditional_core | verified | TODO_VERIFY | 8765 | codraw-icr-v2.tsv=8765 | T05 |
| vague | conditional | conditional_core | verified | TODO_VERIFY | 1677 | train=1677 | T06 |
| clariq | auxiliary | auxiliary | partially_verified | verified | 9176 | train=9176 | T08 |
| safe_agent_bench | challenge_only | challenge | verified | verified | 750 | abstract=100, long_horizon=50, safe_detailed=300, unsafe_detailed=300 | T09 |
| teach | exclude | excluded | excluded | not_applicable | 2275 | — | — |
| teach_tatc | exclude | excluded | excluded | not_applicable | None | — | — |
