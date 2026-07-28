# T28-R2 institutional review packet

## Requested decision

Approve or reject the proposed internal, non-commercial academic use of the
exact six source artifacts listed below for T28 development and training. The
requested approval must be explicit about each right; it must not be inferred
from public availability or from the researcher’s statement.

## Project and intended use

T28 uses a frozen T15 source-train/source-dev view to develop an academic
NLP/robot-command model. The project will retain and transform selected source
records internally, train only for non-commercial academic research, select
development checkpoints using the frozen dev split, and publish aggregate
statistics. Raw source records will not be publicly redistributed. Derived
labels, supervisor/examiner sharing, and trained adapter-weight release remain
separate decisions.

## Sources

AmbiK, IndirectRequests, CoDraw-iCR v2, VAGUE, CLARA, and auxiliary ClariQ.
Immutable local artifact identities and official evidence are in the
authoritative register and `docs/licences/evidence/`. ClariQ is not in the
primary T28 view but remains unresolved in the authoritative register.

## Rights matrix

The complete machine-readable matrix is
`docs/licences/T28_dataset_rights_matrix.json`. All primary-view training and
development decisions are currently `unresolved`; hash-only archival and
project-authored prompt/schema/code release are the only currently recorded
permitted actions. No raw data or adapter weights will be released on this
status.

## Unresolved questions

- Does each exact artifact permit internal retention, processing, non-commercial
  model training, and development checkpoint selection?
- What attribution, notice, share-alike, non-commercial, research-only, and
  redistribution conditions apply?
- Are derived labels, transformed/original records, supervisor copies, and
  trained adapter weights permitted?
- Are inherited SGD, original CoDraw, Qulac, TREC, ClueWeb, or other materials
  covered by compatible terms?

## Public versus licensed

Public access, a repository licence for code, a paper, a citation request, and
an upload by a third party are not dataset permission. The current gate remains
blocked until primary terms, author permission, or a formal institutional
determination covers the relevant action.

## Retention and release plan

Keep the raw source artifacts locally only as required by their terms and retain
hashes, manifests, provenance, and retrieval instructions without raw data in
the public repository. Publish aggregate results and project-authored code only
when allowed. Do not release raw/transformed records or adapters unless the
rights matrix is updated with explicit evidence.

## Contact status

Six author packets are ready in `docs/licences/author_permission_requests/`;
the consolidated action sheet says “ready, not sent”. No communication was
sent automatically.

## Formal decision record (to be completed by authorised approver)

- Approver:
- Role/authority:
- Date:
- Scope (datasets, actions, versions):
- Conditions:
- Evidence document path and SHA-256:
- Decision: pending / approved with conditions / rejected
