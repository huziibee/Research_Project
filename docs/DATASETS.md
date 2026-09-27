# Datasets: acquisition, layout, and rights

The project reads upstream datasets from `data/raw/`. Obtain each source from
its provider, retain the exact revision used in the study, and verify the
recorded hash before running a converter or experiment. A GitHub page being
public does not by itself grant permission to redistribute its contents.

The current rights authority is
`configs/licences/dataset_licence_register.json`. Its internal academic-use
decision does not permit public redistribution of raw records, recoverable
transformed text, or adapter weights. The older
`configs/datasets/licence_provenance_manifest.json` is historical evidence,
not the current permission decision.

| Source and role | Original provider | Expected local file | Study pin or check |
| --- | --- | --- | --- |
| AmbiK, core | [official repository](https://github.com/cog-model/AmbiK-dataset) | `data/raw/AmbiK/ambik_dataset/ambik_test_900.csv` | Git `9d4f60d4224b4183cd35d11233d8114aeaefc2f6`; SHA-256 `eabaeaa26397fc826a138228f1add819594426653cd5375fca09790ecc079d28` |
| IndirectRequests, core | [dataset page](https://huggingface.co/datasets/msamogh/indirect-requests) | `data/raw/IndirectRequests/{train,validation,test}/data-00000-of-00001.arrow` | Hugging Face revision `5b9d22a`; see local manifest hash in the rights register |
| CLARA / SaGC, conditional core | [official repository](https://github.com/jeongeun980906/CLARA-Dataset) | `data/raw/CLARA-Dataset/data/agument.json` | Git `608bfe85b749610385d75304c7265e8204b7a52e`; SHA-256 `f7be73a71a5e5651264fe15dbce4881d727d096e5d322ff2e0081c58de220350` |
| CoDraw-iCR v2, conditional core | [OSF project](https://osf.io/gcjhz/) | `data/raw/codraw-icr-v2/codraw-icr-v2.tsv` | v2 TSV SHA-256 `2ef3981fa67cb8a16e9ba3165053046a38fbc29ed71aadd5a9d5c1033ea009bf` |
| VAGUE, conditional core | [official repository](https://github.com/Hazel-Heejeong-Nam/VAGUE) | `data/raw/vague_bench/data/train-00000-of-00001.parquet` | Local artifact SHA-256 `cf3a9a7655d32ac030c35210bbaad33634327dea3bf1669bf59b0dde5adc1e44` |
| ClariQ, auxiliary only | [official repository](https://github.com/aliannejadi/ClariQ) | `data/raw/ClariQ/data/train.tsv` | Git `46885a544581a0af8aff0681d29e4971807e2912`; SHA-256 `f84245484ab65294f765a76527c6aeea612838b3c4ee51249ab4ae37b1c6161d` |
| SafeAgentBench, challenge only | [dataset page](https://huggingface.co/datasets/safeagentbench/SafeAgentBench) | `data/raw/SafeAgentBench/abstract/train.arrow/data-00000-of-00001.arrow` | Inspect the rights register; no pinned public-release artifact is specified |

TEACh and `teach_tatc` are excluded from the core benchmark. Their Git links
remain in the historical tree; no new researcher needs to fetch them for the
Pilot-120 workflow. VAGUE's current upstream page describes a newer 2.0
release. Do not silently substitute it for the locally hashed study artifact.

## Git-based sources

After reviewing each source's terms, clone the required repositories into
`data/raw/` and check out the exact Git commit listed above. For example:

```sh
mkdir -p data/raw
git clone https://github.com/cog-model/AmbiK-dataset.git data/raw/AmbiK
git -C data/raw/AmbiK checkout 9d4f60d4224b4183cd35d11233d8114aeaefc2f6
```

This example does not fetch the other dataset formats. Obtain the Hugging Face
and OSF material from the linked source pages, place it at the expected path,
and compare its SHA-256 or source manifest to the pinned record. The saved
Arrow layout for IndirectRequests may require an explicit export step; a
provider download is not assumed to reproduce that layout byte-for-byte.

On PowerShell, check a pinned file with:

```powershell
(Get-FileHash -Algorithm SHA256 -LiteralPath 'data/raw/AmbiK/ambik_dataset/ambik_test_900.csv').Hash.ToLower()
```

On Linux or macOS:

```sh
sha256sum data/raw/AmbiK/ambik_dataset/ambik_test_900.csv
```

Compare the result with the table before running an experiment. The path
register in `configs/datasets/dataset_inclusion_register.json` describes
dataset roles; it is an older planning snapshot, so use the current licence
register for rights decisions.

## Pilot-120

Pilot-120 is a separately frozen, 120-record evaluation set, not a downloadable
upstream dataset. Its provenance and hash-only public description are in
`docs/PILOT120.md`. Access to the full source/gold text requires a separate
rights review; it must not be reconstructed by mixing newer upstream versions.
