# Science-closure execution queue

**Purpose:** operational control record for closing every currently unavailable
science claim before any final supervisor dossier is assembled. This is not a
results document and does not convert a planned task into a completed result.

**Last verified state:** 2026-09-02. T39 attempt 6 has five valid fresh GPU
replicas and a terminal `VERIFY_PASSED` reproducibility audit; T45 is complete
locally. This establishes bounded Pilot-120 execution reproducibility, not an
official or generalised result.

## Non-negotiable rule

A row becomes complete only when its stated terminal artifact exists, is
auditable, and has a control status of `PASS`, `FAIL`, or `NOT_COMPUTED` with the actual
evidence gap. A queued Slurm job, an approved protocol, a green preflight, or a
draft document is never completion evidence. Artifact-specific statuses (for
example, `VERIFY_PASSED`) are diagnostic detail, not a substitute control state.

## Live gate

| Gate | State | Evidence | Consequence |
|---|---|---|---|
| T39 static execution contract | `PASS` for fresh GPU inference | `48620`; `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu/t39_provenance_preflight.json` | The immutable GPU-gated archive binds frozen bytes; no CPU or <90-GiB runtime is eligible. |
| T40 availability audit | `PASS` | `48621`; `/home-mscluster/mbangie/t28_r5_src/outputs/pilot_120/t39_20260901_6d71aff_gpu/t40_interpretation_requirements_audit.json` | Existing Pilot gold cannot support intent/CPC/candidate/resolution/wording/silent-resolution claims. |
| T39 five-replay evidence and final audit | `PASS` (`VERIFY_PASSED`) | Five evidence atlases R1--R5; valid job chains `48623`--`48626`, `48627`/`48628`/`48630`/`48631`, `48693`--`48696`, `48701`--`48704`, and `48730`--`48733`; final audit `48791`; `t39_reproducibility_audit.json` SHA-256 `b803771c0fcd4a22b3da344e2d0647ebc46fe2a5d6823a8116eb91978630f081` | All five roots share execution-contract `0f414fc37af907a1e123397463646c85c9edf9db44d8308b079b1efd1974743f`; raw-byte integrity passed and replay content is identical when only finite numeric latency telemetry is normalised. |

## Closure queue

| Queue ID | Closes | Current state | Prerequisites before completion work | Terminal evidence required | Earliest execution lane |
|---|---|---|---|---|---|
| Q39-A | fresh terminal/cost/safety, ambiguity/capability, operations, slices, all-system disagreements, descriptive all-context ablation, deterministic taxonomy, greedy replay reproducibility | `PASS` (`VERIFY_PASSED`): five fresh, valid GPU replicas and final audit | No CPU/under-memory runtime is eligible; each accepted component has attested CUDA/VRAM/node provenance | Five `t39_evidence_atlas.json` files plus latency-aware `t39_reproducibility_audit.json` | Complete; results require bounded, non-official interpretation in the supervisor dossier |
| Q45 / T45 | historical T31 direct-base cost reconciliation and evidence-only early-output slice/disagreement report | `PASS` (`VERIFY_PASSED`) CPU-only, non-official | Exact historical prediction/policy/source/gold bytes and all eight saved system outputs were recovered without inference | Byte/provenance reconciliation plus no-new-inference slice report; hashes recorded in T45 ticket | Complete; excluded from final scientific claims until the full dossier gate |
| Q41 | interpretation/CPC/candidate exactness; resolution; clarification/rejection target and wording; silent-resolution value; human semantic taxonomy coding | CPU readiness verified; **human study not queued; results not computed** | T39 final audit; independent source/sidecar; two independent blinded annotators; adjudication; frozen fixed-system output contract | Sidecar source/annotation/decision manifests, agreement/adjudication artifact, field-score artifact, claim-to-gold crosswalk | Human-review and CPU validation after the gate |
| Q42 | single-ambiguity performance | CPU readiness verified; **new-corpus study not queued; results not computed** | A genuinely new source corpus; licence/source audit; immutable exclusion ledger; double annotation and adjudication; validator proving exactly one unresolved ambiguity instance of exactly one type and no secondary ambiguity | Frozen source/gold/protocol/exclusion manifests, validator result, fixed-system evaluation and support report | Corpus/annotation lane first; cluster inference only after freeze |
| Q43 | separate scene-only, dialogue-only and capability-only effects | CPU readiness verified; **inference not queued; results not computed** | T39 final audit; execution binding to unchanged T39 system/prompt/tokenizer/evaluator; runtime prompt/render/token attestation; frozen eight-condition manifest; paired multiplicity/support analysis plan | Input-byte verifier, condition manifest, paired results artifact, support/multiplicity audit | Cluster after its preflight passes |
| Q44 | narrow family-disjoint held-out-corpus confirmation only | CPU readiness verified; **held-out study not queued; results not computed** | New licensable source; record/paraphrase/scenario-family exclusion audit against Pilot/T42/T41-new-source; double annotation/adjudication; held-out freeze | Licence/source/exclusion/frozen-gold manifests, annotation agreement, fixed-system confirmation artifact | Source and human-review lanes first; cluster only after the freeze |

## CPU-only readiness evidence (2026-09-01)

These local artifacts prove implementation readiness only; they do not close
the corresponding scientific question.

| Workstream | Artifact | SHA-256 | Verified status |
|---|---|---|---|
| T41 | `outputs/readiness_20260901/t41_readiness_contract.json` | `53a5775c5ce9b9e1e2b78c2cbe63162c17bce396a42f6e778d27fd4f2676fb21` | `T41_READINESS_CONTRACT_PASSED` |
| T42 | `outputs/readiness_20260901/t42_readiness_scaffold.json` | `89354b10b9bca7fd8bd3183277ab9e2eda4b45c18404e88a10babad80e5a619a` | `T42_READINESS_SCAFFOLD_PASSED` |
| T43 | `outputs/readiness_20260901/t43_factorial_manifest.json` | `01f1a0ca043d3edce653b67261c10068ee541035ee96b0d5cc18164e5c145b4f` | 960 fixed condition inputs; runtime attestation `NOT_COMPUTED` |
| T43 | `outputs/readiness_20260901/t43_static_verification.json` | `2268203b4f9a61683e0cd3ce661784e0cb757e720968c5853ce34390f3c34a6b` | `T43_STATIC_MANIFEST_VERIFY_PASSED` |
| T44 | `outputs/readiness_20260901/t44_pilot_reference_recovery.json` | `3f06d86aaac776c33d87d65aea13acb1748190f752460ab205e71a291afa19b0` | `PILOT120_REFERENCE_PROVENANCE_RECOVERED` |

## Explicit no-skip checklist

- `NOT_COMPUTED` interpretation and wording metrics remain owned by Q41; they
  cannot be inferred from terminal-route accuracy.
- `NOT_COMPUTED` single-ambiguity performance remains owned by Q42; Pilot-120
  has no eligible record and must not be relabelled into a single-ambiguity set.
- `NOT_COMPUTED` isolated scene/dialogue/capability effects remain owned by Q43;
  T39's all-context removal is descriptive only.
- `NOT_COMPUTED` generalisation remains owned by Q44; a broader claim is never
  substituted for the narrow predeclared confirmation analysis.
- T45 closes the historical direct-base cost-provenance question and its
  no-new-inference saved-output slice/disagreement report only; fresh Q39-A
  outputs still do not retroactively prove any other historical claim.
- Human double coding of semantic taxonomy categories remains Q41. T39's two
  deterministic rule implementations are a cross-check, not a human result.

## Transition policy

1. While Q39 is waiting or running, complete only non-claim-bearing
   preparation: schemas, source/licence audits, annotation packets, validators,
   exclusion-ledger tooling, manifest templates and precision calculations. T45
   was an explicit CPU-only no-new-inference reconciliation exception and cannot
   be used in the supervisor dossier outside the final gate.
2. Q39's final audit and T40 are terminal. Q41 and Q42 still require independent
   source material and blinded human review; these are not silently launched or
   substituted with Pilot-120 proxy scores.
3. Launch Q43 cluster inference only after its frozen condition/input verifier;
   launch Q44 inference only after family-disjoint source and gold freeze.
4. The supervisor dossier may now report Q39/T40/T45 evidence and must retain
   Q41--Q44 as explicitly `NOT_COMPUTED` until their own required artifacts
   exist. This queue remains the authoritative incomplete-work list.
