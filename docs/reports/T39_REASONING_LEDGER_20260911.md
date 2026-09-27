# T39 run reasoning ledger — 2026-09-11

Frozen T39 already stored model thinking. It was not missing from the runs. It
was sitting inside `raw_output` as a `<think>` block and never extracted, so
the traces could not be used for insights.

This note does not modify T39 or T41. It only lifts the existing traces.

Reproducible artifacts:

- `outputs/t39_reasoning_ledger_20260911.jsonl` — 360 rows (120 records × 3 systems), full `<think>` text
  SHA-256 `a75e4e8a9044e0cec96a22d9e0ffe137abb04877d17545db3d6429f87f5b16cc`
- `outputs/t39_reasoning_clusters_20260911.json`
  SHA-256 `7bf55c61024b11538394e7b33451a9781f9ff694f93e4485088119d72fa4ca45`
- extractor: `scripts/extract_t39_reasoning_ledger.py`

## What was actually stored

| Fact | Full manager (n=120) |
|---|---:|
| `<think>` present and closed | 120/120 |
| Truncated unclosed think | 0/120 |
| Non-null `intent_summary` | 0/120 |
| Think reuses a scene clock or tag | 100/120 |
| Think is mainly about filling the analysis JSON | 118/120 |
| Think mentions the human dialogue / “treat as a request” | 48/120 |

The model was not silent. It was reasoning about **which schema labels to emit**,
not about **what the robot should do next**. `intent_summary` is null on every
frozen record, and CPC slots are all `unknown`, so the router only sees
unresolved slots and fail-safes to clarify.

Example, CA-0007. The nurse said “treat that as a request.” The think names
10:39, 11:00, and 15:00, then still asks “destination, time?” Gold wanted
clarify here; the same pattern on gold-execute cases is the over-ask problem.

## Why gold-execute cases were asked (75/76)

Full manager predicted execute 0 times. 75 gold-execute records went to clarify.
Blind judges still scored the goal trace correct on 73 of those 75.

| Cluster | n | What the think is doing | Action |
|---|---:|---|---|
| Asked for slots already licensed by the scene | 52 | Names PENDING/COMPLETE tags, handbook times, assigned destinations, then asks for those same slots | Do not ask; bind the scene fact into CPC and execute if capable/safe |
| Named ambiguity, then asked | 16 | Often the same pattern with a slot alias (`temporal` instead of `time`) | Normalise slot names; treat handbook-defined “shortly” as resolved |
| Knew it was a request, still asked for scene slots | 5 | Quotes the human (“handle it means move after weighing”) and still asks destination/object | Speech-act is recovered in prose; the JSON still marks slots unresolved |
| Treated an executable job as an unverified condition | 2 | Conditional capability with no unsafe/incapable evidence | Stop mapping “after the check” onto `unverified_conditional_capability` |

Router rules on those 75: `dependent_compound_ambiguities` 37, `default_clarify`
24, `unverified_conditional_capability` 14. None of those rules can execute.
Goal-first counterfactual routing of the **same frozen analyses** would execute
61 of these 75. That is a policy change, not a T39 rewrite.

## Other clusters (the remaining 45)

| Cluster | n | Read as |
|---|---:|---|
| Asked when gold also wanted a question | 23 | Correct route for the wrong reason is still possible; several of these still ask for scene-licensed slots |
| Asked instead of refusing | 11 | Over-cautious: capability/safety should have been a refusal, not another question |
| Refused when gold refused | 10 | The traces that work: think names the bolted fixture / weight limit / no-access zone and the router refuses |
| Refused a gold-execute case | 1 | CA-0239, `known_incapable` |

## What to change so future runs are inspectable

1. **Keep writing `<think>` to logs**, but also persist a structured
   `reasoning_excerpt` plus filled CPC / `intent_summary` on every analysis.
   Frozen T39 left those fields empty, which is why the scores could not explain
   themselves.
2. **Separate schema-filling from action-planning.** The model spends the think
   budget listing allowed JSON keys. The next versioned prompt should ask for
   “what job, using which scene facts” before “which ambiguity labels.”
3. **Do not wait for a new model to stop over-asking.** On this frozen set, the
   think already names the job in most gold-execute cases. The conservative
   router is what turns that into a question.
4. **Query the ledger, do not re-read 120 raw files.** Filter
   `outputs/t39_reasoning_ledger_20260911.jsonl` by `reasoning_cluster`,
   `system_id`, or `record_id`.

T39 numbers stay frozen. This ledger is an interpretation layer on the existing
`raw_output`, not a new official result.
