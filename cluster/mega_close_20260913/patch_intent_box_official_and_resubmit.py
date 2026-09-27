#!/usr/bin/env python3
"""Allow official adapters in intent-box, then resubmit mega-official."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

INTENT_PATHS = [
    Path("/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/scripts/evaluate_pilot_120_intent_box.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913/scripts/evaluate_pilot_120_intent_box.py"),
    Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913/scripts/evaluate_pilot_120_intent_box.py"),
]
IDENTITY = Path(
    "/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/"
    "early_pilot_package_excluding_clara1170_v1/adapter_identity.json"
)
SUBMIT = Path(
    "/home-mscluster/mbangie/t12-hpc/code/mega_close-20260913/cluster/mega_close_20260913/submit_official.sh"
)

OLD = """        if adapter_identity.get("valid_for_official_use") is True:
            raise SystemExit("refusing_to_treat_unofficial_adapter_as_official")
        if adapter_identity.get("selected_adapter") is not True and not args.allow_unofficial_adapter:
            raise SystemExit("unofficial_adapter_needs_allow_flag")
        adapter_id = str(adapter_identity.get("adapter_id") or "unofficial-fine-tune")
"""

NEW = """        official = adapter_identity.get("valid_for_official_use") is True
        selected = adapter_identity.get("selected_adapter") is True
        if official:
            if not selected:
                raise SystemExit("official_adapter_requires_selected")
            if args.allow_unofficial_adapter:
                raise SystemExit("refusing_unofficial_flag_on_official_adapter")
        elif not selected and not args.allow_unofficial_adapter:
            raise SystemExit("unofficial_adapter_needs_allow_flag")
        adapter_id = str(
            adapter_identity.get("adapter_id")
            or ("official-fine-tune" if official else "unofficial-fine-tune")
        )
"""

OLD_MANIFEST = '"unofficial_fine_tune": args.adapter is not None,'
NEW_MANIFEST = (
    '"unofficial_fine_tune": bool(args.adapter) and not ('
    '(adapter_identity or {}).get("valid_for_official_use") is True),'
)


def patch(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if "official_adapter_requires_selected" in text:
        return "already_patched"
    if OLD not in text:
        raise SystemExit(f"old_guard_missing:{path}")
    text = text.replace(OLD, NEW, 1)
    if OLD_MANIFEST in text:
        text = text.replace(OLD_MANIFEST, NEW_MANIFEST, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    return "patched"


def main() -> int:
    ident = json.loads(IDENTITY.read_text(encoding="utf-8"))
    if ident.get("selected_adapter") is not True or ident.get("valid_for_official_use") is not True:
        raise SystemExit(f"identity_not_official:{ident}")
    print("identity_ok", {k: ident.get(k) for k in ("selected_adapter", "valid_for_official_use", "adapter_scale", "adapter_id")})

    first = None
    for path in INTENT_PATHS:
        if not path.is_file():
            print("skip_missing", path)
            continue
        status = patch(path)
        print(status, path)
        if first is None:
            first = path
        elif status == "patched" and first is not None:
            shutil.copy2(first, path)
            print("synced_from_first", path)

    q = subprocess.check_output(["squeue", "-u", "mbangie", "-h"], text=True).strip()
    if q:
        print("queue_not_empty")
        print(q)
        raise SystemExit(3)
    subprocess.check_call(["bash", str(SUBMIT)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
