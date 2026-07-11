# Dataset Licence Register

Register schema: `2.0.0`  
Authoritative register: `configs/licences/dataset_licence_register.json`  
Historical evidence only: `configs/datasets/licence_provenance_manifest.json`

This summary records verification status and permission gates. It does not
provide legal conclusions. Unknown permission fields are `null` and must never
be treated as true.

## Gate rule

For `unresolved` or `stated_unverified` sources:

- completed local preservation and migration may remain recorded;
- future model training is blocked;
- official evaluation is blocked;
- redistribution is blocked;
- public release is blocked.

A source becomes usable for blocked activities only when permission is verified
with evidence or an explicit institutional/legal decision is recorded.

## Sources

| Dataset | Verification status | Training | Evaluation | Redistribution |
| --- | --- | --- | --- | --- |
| ambik | unresolved | blocked | blocked | blocked |
| indirect_requests | unresolved | blocked | blocked | blocked |
| clara | unresolved | blocked | blocked | blocked |
| codraw_icr_v2 | stated_unverified | blocked | blocked | blocked |
| vague | unresolved | blocked | blocked | blocked |
| clariq | unresolved | blocked | blocked | blocked |
| safe_agent_bench | unresolved | blocked | blocked | blocked |
| manual_compound | not_yet_acquired | blocked | blocked | blocked |
