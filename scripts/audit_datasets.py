#!/usr/bin/env python3
"""Run the automated dataset audit (T02)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from ambiguity_manager.data_audit.config import (  # noqa: E402
    default_licence_manifest_path,
    default_register_path,
    load_inclusion_register,
    load_licence_manifest,
)
from ambiguity_manager.data_audit.report import (  # noqa: E402
    generate_audit_markdown,
    generate_inclusion_markdown,
    generate_licence_markdown,
)
from ambiguity_manager.data_audit.runner import run_audit  # noqa: E402
from ambiguity_manager.data_audit.writer import write_audit_json, write_text_report  # noqa: E402
from ambiguity_manager.paths import ProjectPaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dataset audit over data/raw (read-only).")
    parser.add_argument(
        "--register",
        type=Path,
        default=None,
        help="Path to dataset inclusion register JSON (default: configs/datasets/...)",
    )
    parser.add_argument(
        "--licence-manifest",
        type=Path,
        default=None,
        help="Path to licence/provenance manifest JSON",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Audit JSON output path (default: outputs/metrics/dataset_audit.json)",
    )
    args = parser.parse_args()

    paths = ProjectPaths.from_repo_root(_REPO_ROOT)
    paths.ensure_project_dirs()

    register_path = args.register or default_register_path()
    manifest_path = args.licence_manifest or default_licence_manifest_path()
    output_json = args.output_json or (paths.outputs / "metrics" / "dataset_audit.json")

    audit = run_audit(
        repo_root=paths.root,
        register_path=register_path,
        manifest_path=manifest_path,
    )
    write_audit_json(audit, output_json)

    register = load_inclusion_register(register_path)
    manifest = load_licence_manifest(manifest_path)
    write_text_report(generate_audit_markdown(audit), paths.docs / "mapping" / "dataset_audit.md")
    write_text_report(
        generate_inclusion_markdown(register, audit),
        paths.docs / "decisions" / "dataset_inclusion_register.md",
    )
    write_text_report(
        generate_licence_markdown(manifest, audit),
        paths.docs / "dataset_cards" / "source_licence_manifest.md",
    )

    print(f"Wrote audit JSON: {output_json}")
    print(f"Wrote markdown: {paths.docs / 'mapping' / 'dataset_audit.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
