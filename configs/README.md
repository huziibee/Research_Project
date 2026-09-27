# Configuration and contracts

- `evaluation/` contains frozen label, judging, denominator, and prompt
  contracts, including `pilot_120_v1.json` and `pilot120_intent_v1/`.
- `datasets/` records source versions, roles, and historical provenance.
- `licences/dataset_licence_register.json` is the current rights decision
  register; source evidence is in `docs/licences/`.
- `model/` and `environments/` record model identities, runtime/container
  assumptions, and historical verification. They do not contain weights.
- `governance/` and `research/` preserve decisions and research boundaries.

Read [setup and recovery](../docs/SETUP_AND_RECOVERY.md) before running an
experiment on a new machine. Changes to frozen contracts require a new
versioned file and provenance, not an in-place overwrite.
