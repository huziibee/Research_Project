#!/usr/bin/env python3
"""Prebuild lm-format-enforcer TokenEnforcerTokenizerData regular_tokens for Qwen3-8B.

Writes a JSON cache under T12_TRAINING_SITE_PACKAGES/caches/ so T27C constrained
decoding does not rebuild the ~150k-token table on every GPU job.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    repo = os.environ.get("T12_BASE_REPO", "Qwen/Qwen3-8B")
    rev = os.environ.get(
        "T12_BASE_REVISION", "b968826d9c46dd6066d109eabc6255188de91218"
    )
    site = Path(
        os.environ.get(
            "T12_TRAINING_SITE_PACKAGES",
            str(Path.home() / "t12-hpc" / "training-site-packages"),
        )
    )
    sys.path.insert(0, str(site))
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(repo, revision=rev, local_files_only=True)
    vocab_size = max(int(tok.vocab_size), int(len(tok)))
    cache_dir = site / "caches"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"lmfe_regular_tokens_{repo.replace('/', '__')}_{rev[:12]}_{vocab_size}.json"
    if cache_path.is_file():
        print(f"CACHE_EXISTS {cache_path} bytes={cache_path.stat().st_size}")
        return 0

    token_0 = int(tok.encode("0")[-1])
    special_ids = set(int(x) for x in (tok.all_special_ids or []))
    regular_tokens: list[list[object]] = []
    chunk = 4096
    t0 = time.time()
    for start in range(0, vocab_size, chunk):
        idxs = [i for i in range(start, min(start + chunk, vocab_size)) if i not in special_ids]
        if not idxs:
            continue
        decoded_after_0 = tok.batch_decode([[token_0, i] for i in idxs])
        decoded_regular = tok.batch_decode([[i] for i in idxs])
        for token_idx, after_0, regular in zip(idxs, decoded_after_0, decoded_regular):
            after_0_s = after_0[1:] if after_0 else ""
            is_word_start = len(after_0_s) > len(regular or "")
            regular_tokens.append([token_idx, after_0_s, bool(is_word_start)])
        if start % (chunk * 8) == 0:
            print(
                f"progress {min(start + chunk, vocab_size)}/{vocab_size} "
                f"elapsed={time.time() - t0:.1f}s",
                flush=True,
            )

    payload = {
        "repository": repo,
        "revision": rev,
        "vocab_size": vocab_size,
        "eos_token_id": tok.eos_token_id,
        "regular_tokens": regular_tokens,
    }
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache_path)
    print(
        f"CACHE_WRITTEN {cache_path} tokens={len(regular_tokens)} "
        f"elapsed={time.time() - t0:.1f}s bytes={cache_path.stat().st_size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
