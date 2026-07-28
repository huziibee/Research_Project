# T28-R4 Handover

T28-R4 is **BLOCKED before model loading** by the explicit canonical/permitted hash-integrity gate after bounded recovery. R3 was preserved in `67fddf5`; the final implementation/evidence state is `7dcb1a3`.

The frozen local corpus and manifests reproduce all authoritative hashes and counts. Three Slurm job IDs are preserved: `22708`, `22710`, and `22715`. The first was an implementation identity mismatch; the two recovery attempts failed with `canonical_hash_mismatch`. No checkpoint, dev inference, adapter selection, package, clean-load verification, or manager configuration update exists.

No protected data was accessed, no public release occurred, and T29 did not begin. Resume only after the remote archive/extraction path produces independently verified canonical, permitted-view, train-manifest, and dev-manifest hashes; do not alter the frozen scientific plan.
