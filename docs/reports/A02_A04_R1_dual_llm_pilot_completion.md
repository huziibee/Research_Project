# A02-A04-R1 dual-LLM pilot completion report

## Outcome

`BLOCKED`

The frozen Mistral annotator could not complete its structured-output preload canary after the one permitted isolated runtime repair. No pilot annotation was accepted, so GLM was not launched and no agreement or review packet was created.

## Frozen inputs and runtime

- Pilot: 40 records; SHA-256 `81d56440801c24a68032e3512dc7c6ca8c4fbd2317bdf56a78cf0d36172e6de1`.
- Annotator A: `mistralai/Mistral-Small-4-119B-2603-NVFP4` at `b1a9048590131d38491bd23a7c9f6ed0962f0358`.
- Runtime: Apptainer vLLM `0.20.1`, Torch `2.11.0+cu130`, Transformers `5.7.0`, compressed-tensors `0.15.0.1`, mistral-common `1.11.1`.
- Node: `mscluster110`, NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 97,887 MiB VRAM, 110G exclusive allocation, offline model use.

## Evidence

- Initial clean-node canary job `23083` loaded all Mistral checkpoint infrastructure and reached the structured canary. It failed in the Triton MLA decode kernel with `Cannot make_shape_compatible: incompatible dimensions at index 1: 256 and 512`.
- One authorised runtime repair was applied: identical model/configuration with vLLM `--enforce-eager`, disabling torch.compile and CUDA graphs. Retry job `23087` reproduced the identical Triton MLA error.
- Raw logs are preserved under the cluster run directories `a03-pilot-23083-20260728` and `a03-pilot-23087-20260728`, including server startup, checkpoint loading, kernel selection, and failed HTTP attempts.
- Each failed allocation was terminated after the engine had already failed; no vLLM/EngineCore process remained and GPU usage returned to 2 MiB.

## Boundaries honoured

- No full 400-600 record run was launched.
- No protected data was accessed.
- T15, T27, T28, and T29 were not modified.
- No substitute annotator was used.
- No Mistral output was accepted as a pilot annotation; no GLM annotation was attempted, preserving blind independence.

## Required next authority

A future run requires a newly pinned vLLM/Triton runtime that demonstrably supports this exact native NVFP4 Mistral MLA checkpoint on Blackwell. That would exceed the one permitted runtime repair and must be separately authorised.
