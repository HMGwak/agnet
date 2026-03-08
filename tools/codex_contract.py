from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
CODEX_CONTRACT_DIR = ROOT_DIR / "runtime" / "codex" / "contract"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.codex_contract import (  # noqa: E402
    MANIFEST_FILE_NAME,
    CodexContractError,
    apply_contract,
    load_contract,
    verify_contract,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply or verify the repository Codex contract bundle."
    )
    parser.add_argument("command", choices=("apply", "verify"))
    parser.add_argument("--root", type=Path, default=CODEX_CONTRACT_DIR)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=CODEX_CONTRACT_DIR / MANIFEST_FILE_NAME,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        spec = load_contract(args.manifest)
        if args.command == "apply":
            changed_paths = apply_contract(spec, args.root)
            if changed_paths:
                for path in changed_paths:
                    print(path)
            else:
                print("Codex contract already in sync.")
            return 0

        drifts = verify_contract(spec, args.root)
        if drifts:
            for drift in drifts:
                print(f"{drift.reason}: {drift.path}")
            return 1
        print("Codex contract is in sync.")
        return 0
    except CodexContractError as exc:
        print(f"Codex contract error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
