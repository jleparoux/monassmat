from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess

from monassmat.config import settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restore the MonAssmat PostgreSQL database from a .dump file."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("docker", "local"),
        default="docker",
        help="Restore using docker exec or local pg_restore.",
    )
    parser.add_argument("--container", default="monassmat-db")
    parser.add_argument("--user", default="monassmat")
    parser.add_argument("--db", default="monassmat")
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL for local mode (defaults to DATABASE_URL or settings).",
    )
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Restore data only (no schema).",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Restore schema only (no data).",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not drop existing objects before restoring.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_path: Path = args.input
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    if args.data_only and args.schema_only:
        raise SystemExit("Choose either --data-only or --schema-only, not both.")

    clean_args = [] if args.no_clean else ["--clean", "--if-exists"]
    restore_args = []
    if args.data_only:
        restore_args.append("--data-only")
    elif args.schema_only:
        restore_args.append("--schema-only")

    if args.mode == "docker":
        cmd = [
            "docker",
            "exec",
            "-i",
            args.container,
            "pg_restore",
            "-U",
            args.user,
            "-d",
            args.db,
            *clean_args,
            *restore_args,
        ]
    else:
        db_url = args.db_url or os.environ.get("DATABASE_URL") or settings.database_url
        cmd = ["pg_restore", "-d", db_url, *clean_args, *restore_args]

    with input_path.open("rb") as handle:
        subprocess.run(cmd, check=True, stdin=handle)

    print("Restore complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
