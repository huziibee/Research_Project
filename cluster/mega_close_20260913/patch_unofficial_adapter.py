#!/usr/bin/env python3
"""Patch unofficial PEFT loads. Never flips selected_adapter / valid_for_official_use."""
from __future__ import annotations

import re
from pathlib import Path

ROOTS = [
    Path("/home-mscluster/mbangie/t12-hpc/code/final_close-20260913"),
    Path("/home-mscluster/mbangie/t12-hpc/code/temp_sweep-20260913"),
]

NEW_FN = '''def selected_adapter_identity(
    identity: Mapping[str, Any],
    *,
    adapter_scale: float,
    allow_unofficial: bool = False,
) -> str:
    """Return adapter identity for PEFT load, including inference scale.

    Official selected adapters must set selected_adapter=true. Unofficial
    research adapters may load only when allow_unofficial=True; they still
    must match the frozen base model / revision, and never claim
    valid_for_official_use.
    """
    selected = identity.get("selected_adapter", identity.get("selected_adapter"))
    official = identity.get("valid_for_official_use", identity.get("valid_for_official_use"))
    if official is True and selected is not True:
        raise ValueError("pilot_adapter_official_flag_without_selected")
    if selected is not True:
        if not allow_unofficial:
            raise ValueError("pilot_adapter_requires_selected_t28_adapter")
        if official is True:
            raise ValueError("refusing_unofficial_load_marked_official")

    base = identity.get("base_model", identity.get("base_model"))
    rev = identity.get("base_revision", identity.get("base_revision"))
    if isinstance(base, str) and "@" in base and not rev:
        base, rev = base.rsplit("@", 1)
    if base != BASE_MODEL or rev != BASE_REVISION:
        raise ValueError("pilot_adapter_base_identity_mismatch")

    adapter_id = str(
        identity.get("adapter_id")
        or identity.get("adapter_id")
        or identity.get("adapter_id")
        or ""
    ).strip()
    if not adapter_id:
        raise ValueError("pilot_adapter_identity_missing_adapter_id")

    if "adapter_scale" in identity or "adapter_scale" in identity:
        expected_scale = float(identity.get("adapter_scale", identity.get("adapter_scale")))
        if expected_scale <= 0 or abs(expected_scale - adapter_scale) > 1e-12:
            raise ValueError("pilot_adapter_scale_identity_mismatch")
    elif not allow_unofficial:
        raise ValueError("pilot_adapter_identity_missing_adapter_scale")
    return adapter_id


'''


def replace_fn(text: str) -> str:
    # Keep whatever constant names the file already uses.
    local_fn = NEW_FN
    if "BASE_MODEL" in text and "BASE_MODEL" not in text.split("selected_adapter_identity", 1)[0][-400:]:
        # file may use BASE_MODEL
        if re.search(r"^BASE_MODEL\s*=", text, re.M) and not re.search(r"^BASE_MODEL\s*=", text, re.M):
            local_fn = local_fn.replace("BASE_MODEL", "BASE_MODEL").replace("BASE_REVISION", "BASE_REVISION")
    if re.search(r"^BASE_MODEL\s*=", text, re.M):
        local_fn = local_fn.replace("BASE_MODEL", "BASE_MODEL").replace("BASE_REVISION", "BASE_REVISION")
    # Detect actual constants
    if "BASE_MODEL =" in text or 'BASE_MODEL =' in text:
        const_model = "BASE_MODEL" if "BASE_MODEL =" in text else "BASE_MODEL"
        const_rev = "BASE_REVISION" if "BASE_REVISION =" in text else "BASE_REVISION"
        # read exact names
        mm = re.search(r"^(BASE_[A-Z_]+)\s*=\s*\"[^\"]+\"", text, re.M)
        mr = None
        names = re.findall(r"^(BASE_[A-Z_]+)\s*=", text, re.M)
        if len(names) >= 2:
            local_fn = local_fn.replace("BASE_MODEL", names[0]).replace("BASE_REVISION", names[1])
    m = re.search(
        r"def selected_adapter_identity\([\s\S]*?\n    return adapter_id\n",
        text,
    )
    if not m:
        raise RuntimeError("selected_adapter_identity_not_found")
    return text[: m.start()] + local_fn + text[m.end() :]


def ensure_cli_flag(text: str) -> str:
    if "--allow-unofficial-adapter" in text:
        return text
    needle = 'parser.add_argument("--adapter-scale", type=float, default=1.0)\n'
    if needle not in text:
        raise RuntimeError("adapter_scale_arg_not_found")
    insert = (
        needle
        + "    parser.add_argument(\n"
        + '        "--allow-unofficial-adapter",\n'
        + '        action="store_true",\n'
        + '        help="Allow PEFT load when selected_adapter is false (still unofficial).",\n'
        + "    )\n"
    )
    return text.replace(needle, insert, 1)


def ensure_limit_flag(text: str) -> str:
    if 'parser.add_argument("--limit"' in text:
        return text
    needle = '        help="Allow PEFT load when selected_adapter is false (still unofficial).",\n    )\n'
    if needle not in text:
        return text
    return text.replace(
        needle,
        needle
        + '    parser.add_argument("--limit", type=int, default=0, help="If >0, only the first N source rows.")\n',
        1,
    )


def wire_call(text: str) -> str:
    if "allow_unofficial=" in text and "allow_unofficial_adapter" in text:
        return text
    out, n = re.subn(
        r"selected_adapter_identity\(\s*([^,\)]+)\s*,\s*adapter_scale=([^,\)]+)\)",
        r"selected_adapter_identity(\1, adapter_scale=\2, allow_unofficial=bool(getattr(args, 'allow_unofficial_adapter', False)))",
        text,
        count=3,
    )
    if n:
        return out
    out = text.replace(
        "selected_adapter_identity(identity, adapter_scale=args.adapter_scale)",
        "selected_adapter_identity(identity, adapter_scale=args.adapter_scale, allow_unofficial=bool(getattr(args, 'allow_unofficial_adapter', False)))",
    )
    if out == text:
        raise RuntimeError("call_site_not_patched")
    return out


def ensure_limit_slice(text: str) -> str:
    if "args.limit" in text and "source_rows = source_rows[" in text:
        return text
    # goal_first style already has limit handling often
    if "if args.limit and args.limit > 0:" in text:
        return text
    m = re.search(r"source_rows = [^\n]+\n", text)
    if not m:
        return text
    # Insert after first source_rows assignment in main()
    idx = text.find("source_rows =", text.find("def main"))
    if idx < 0:
        return text
    end = text.find("\n", idx)
    line = text[idx:end]
    insert = (
        line
        + "\n    if getattr(args, 'limit', 0) and args.limit > 0:\n"
        + "        source_rows = source_rows[: int(args.limit)]"
    )
    return text[:idx] + insert + text[end:]


def patch_direct(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_fn(text)
    text = ensure_cli_flag(text)
    text = ensure_limit_flag(text)
    text = wire_call(text)
    text = ensure_limit_slice(text)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"ok_direct:{path}")


def patch_consumer(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = ensure_cli_flag(text)
    text = wire_call(text)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"ok_consumer:{path}")


def patch_sweep(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count("--allow-unofficial-adapter") >= 2:
        print(f"skip_sweep:{path}")
        return
    # Add flag to every adapter argv construction.
    text2 = text
    text2 = re.sub(
        r'(\["--adapter", adapter, "--adapter-identity", identity, "--adapter-scale", scale\])',
        '["--adapter", adapter, "--adapter-identity", identity, "--adapter-scale", scale, "--allow-unofficial-adapter"]',
        text2,
    )
    text2 = re.sub(
        r'("--adapter-scale", scale,)(\s*")',
        r'\1\n        "--allow-unofficial-adapter",\2',
        text2,
        count=5,
    )
    path.write_text(text2, encoding="utf-8", newline="\n")
    print(f"ok_sweep:{path}")


def main() -> int:
    for root in ROOTS:
        direct = root / "scripts" / "evaluate_pilot_120_direct_base.py"
        if direct.is_file():
            patch_direct(direct)
        for name in (
            "evaluate_goal_first_manager_v2.py",
            "evaluate_pilot_120_manager_systems.py",
        ):
            p = root / "scripts" / name
            if p.is_file():
                patch_consumer(p)
        for sweep in root.glob("cluster/**/sweep.sbatch"):
            patch_sweep(sweep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
