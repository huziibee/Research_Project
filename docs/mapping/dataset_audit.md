# Dataset Audit Report

- Audit schema: `1.1.0`
- Generated at: `2026-07-10T14:42:05+00:00`
- Tool version: `0.1.0`
- Git commit: `dde9596589d1abea51737d1dac0b098c2e4e3c01`

Status fields are separated: payload verification (technical readability/counts), mapping verification (project taxonomy mapping), and licence status (evidence only).

## Summary

| Metric | Count |
| --- | --- |
| Datasets registered | 9 |
| Payload verified | 6 |
| Payload partially verified | 1 |
| Payload metadata only | 0 |
| Payload blocked | 0 |
| Excluded | 2 |
| Missing (not blocking) | 5 |

## Per-dataset outcomes

### AmbiK (`ambik`)

| Field | Value |
| --- | --- |
| Payload verification | verified |
| Mapping verification | TODO_VERIFY |
| Licence status | unresolved |
| Inclusion decision | include |
| Role | core |
| Total authoritative rows | 1000 |
| Component counts | primary=1000 |
| Filesystem present | True |
| Code only | False |
| Submodule commit | 9d4f60d4224b4183cd35d11233d8114aeaefc2f6 |

Authoritative files:

| Path | Rows | Readable | SHA-256 (prefix) |
| --- | --- | --- | --- |
| AmbiK/AmbiK_data.csv | 1000 | True | 98bb4677eb7fad00… |

Mapping risks:
- `TODO_VERIFY_LABEL_MAPPING` field `ambiguity_type`: Map AmbiK ambiguity types to project taxonomy in T03

### CLARA / SaGC (`clara`)

| Field | Value |
| --- | --- |
| Payload verification | verified |
| Mapping verification | TODO_VERIFY |
| Licence status | unresolved |
| Inclusion decision | conditional |
| Role | conditional_core |
| Total authoritative rows | 5345 |
| Component counts | agument.json=5345 |
| Filesystem present | True |
| Code only | False |
| Submodule commit | 608bfe85b749610385d75304c7265e8204b7a52e |

Authoritative files:

| Path | Rows | Readable | SHA-256 (prefix) |
| --- | --- | --- | --- |
| CLARA-Dataset/data/agument.json | 5345 | True | f7be73a71a5e5651… |

Mapping risks:
- `TODO_VERIFY_LABEL_MAPPING` field `label`: CLARA labels 0-3 route mapping deferred to T07

### ClariQ (`clariq`)

| Field | Value |
| --- | --- |
| Payload verification | partially_verified |
| Mapping verification | verified |
| Licence status | unresolved |
| Inclusion decision | auxiliary |
| Role | auxiliary |
| Total authoritative rows | 9176 |
| Component counts | train=9176 |
| Filesystem present | True |
| Code only | False |
| Submodule commit | 46885a544581a0af8aff0681d29e4971807e2912 |

Authoritative files:

| Path | Rows | Readable | SHA-256 (prefix) |
| --- | --- | --- | --- |
| ClariQ/data/train.tsv | 9176 | True | f84245484ab65294… |

Warnings:
- `split_overlap`: 7 overlapping IDs across ClariQ/data/train.tsv, ClariQ/data/dev.tsv on ['question_id']

### CoDraw-iCR v2 (`codraw_icr_v2`)

| Field | Value |
| --- | --- |
| Payload verification | verified |
| Mapping verification | TODO_VERIFY |
| Licence status | stated_unverified |
| Inclusion decision | conditional |
| Role | conditional_core |
| Total authoritative rows | 8765 |
| Component counts | codraw-icr-v2.tsv=8765 |
| Filesystem present | True |
| Code only | False |
| Submodule commit | None |

Authoritative files:

| Path | Rows | Readable | SHA-256 (prefix) |
| --- | --- | --- | --- |
| codraw-icr-v2/codraw-icr-v2.tsv | 8765 | True | 2ef3981fa67cb8a1… |

Mapping risks:
- `TODO_VERIFY_LABEL_MAPPING` field `drawer`: Clarification mapping deferred to T05

### IndirectRequests (`indirect_requests`)

| Field | Value |
| --- | --- |
| Payload verification | verified |
| Mapping verification | TODO_VERIFY |
| Licence status | unresolved |
| Inclusion decision | include |
| Role | core |
| Total authoritative rows | 906 |
| Component counts | test=388, train=246, validation=272 |
| Filesystem present | True |
| Code only | False |
| Submodule commit | None |

Authoritative files:

| Path | Rows | Readable | SHA-256 (prefix) |
| --- | --- | --- | --- |
| IndirectRequests/train/data-00000-of-00001.arrow | 246 | True | b4a43371c025b21b… |
| IndirectRequests/validation/data-00000-of-00001.arrow | 272 | True | 3376a4c83fc266f9… |
| IndirectRequests/test/data-00000-of-00001.arrow | 388 | True | ee93197e8a7fed4e… |

Mapping risks:
- `TODO_VERIFY_LABEL_MAPPING` field `utterance`: Field-to-canonical mapping deferred to T04

### SafeAgentBench (`safe_agent_bench`)

| Field | Value |
| --- | --- |
| Payload verification | verified |
| Mapping verification | verified |
| Licence status | unresolved |
| Inclusion decision | challenge_only |
| Role | challenge |
| Total authoritative rows | 750 |
| Component counts | abstract=100, long_horizon=50, safe_detailed=300, unsafe_detailed=300 |
| Filesystem present | True |
| Code only | False |
| Submodule commit | None |

Authoritative files:

| Path | Rows | Readable | SHA-256 (prefix) |
| --- | --- | --- | --- |
| SafeAgentBench/abstract/train.arrow/data-00000-of-00001.arrow | 100 | True | 25368c696957b024… |
| SafeAgentBench/unsafe_detailed/train.arrow/data-00000-of-00001.arrow | 300 | True | 1288643366bcff97… |
| SafeAgentBench/safe_detailed/train.arrow/data-00000-of-00001.arrow | 300 | True | c63906f7389b731d… |
| SafeAgentBench/long_horizon/train.arrow/data-00000-of-00001.arrow | 50 | True | b36a68ac1f1302e4… |

### TEACh (`teach`)

| Field | Value |
| --- | --- |
| Payload verification | excluded |
| Mapping verification | not_applicable |
| Licence status | stated_unverified |
| Inclusion decision | exclude |
| Role | excluded |
| Total authoritative rows | 2275 |
| Component counts | — |
| Filesystem present | True |
| Code only | False |
| Submodule commit | 903191e256da866a603d1bbfb21db34e0874392d |

### teach_tatc (`teach_tatc`)

| Field | Value |
| --- | --- |
| Payload verification | excluded |
| Mapping verification | not_applicable |
| Licence status | stated_unverified |
| Inclusion decision | exclude |
| Role | excluded |
| Total authoritative rows | None |
| Component counts | — |
| Filesystem present | True |
| Code only | True |
| Submodule commit | 634c01145069007f0bdb245617daa8ecde5c092e |

Warnings:
- `code_only_tree`: directory appears code-only without data payloads

### VAGUE (`vague`)

| Field | Value |
| --- | --- |
| Payload verification | verified |
| Mapping verification | TODO_VERIFY |
| Licence status | unresolved |
| Inclusion decision | conditional |
| Role | conditional_core |
| Total authoritative rows | 1677 |
| Component counts | train=1677 |
| Filesystem present | True |
| Code only | False |
| Submodule commit | None |

Authoritative files:

| Path | Rows | Readable | SHA-256 (prefix) |
| --- | --- | --- | --- |
| vague_bench/data/train-00000-of-00001.parquet | 1677 | True | cf3a9a7655d32ac0… |

Mapping risks:
- `TODO_VERIFY_LABEL_MAPPING` field `direct`: Context-dependent mapping deferred to T06

## Missing datasets (not blocking)

| Dataset | Status | Planned rows |
| --- | --- | --- |
| dynamic_rdmm | MISSING_NOT_BLOCKING | 19721 |
| refcoco | MISSING_NOT_BLOCKING | 378784 |
| referit3d | MISSING_NOT_BLOCKING | 323177 |
| cmc | MISSING_NOT_BLOCKING | 1571 |
| manual_compound | MISSING_NOT_BLOCKING | None |

## Excluded artifacts

| Path | Reason |
| --- | --- |
| data/raw/.venv | accidental virtualenv, not a dataset |
| data/raw/vague_bench/.cache | HuggingFace download cache stubs, not authoritative payload |
