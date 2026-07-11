# Protected Data Policy

## Lifecycle

| Phase | Rule |
| --- | --- |
| Before T15 | No protected benchmark exists. |
| T15 construction | Split creation, leakage checks, hashing, and sealing are permitted under the T15 process. |
| After T15 seal | No protected content in prompts, debugging, tuning, threshold selection, model selection, tests, screenshots, or external AI tools. |
| T29 | Protocol verification and protected-execution approval. |
| T30 | Controlled protected execution through the frozen runner only. |

## Access and incidents

- Access events are logged in `docs/governance/logs/protected_access_log.jsonl`.
- External AI tools must not receive protected data once sealed.
- Local models may access protected data only in the T30 controlled runner.
- Contamination requires an incident record, deviation, and protocol invalidation review.

Machine-readable policy: `configs/governance/protected_data_policy.json`
