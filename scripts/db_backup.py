from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
import subprocess

from monassmat.config import settings


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("backups") / f"monassmat_{timestamp}.dump"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backup the MonAssmat PostgreSQL database."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_path(),
        help="Output .dump file path (default: backups/monassmat_YYYYMMDD_HHMMSS.dump).",
    )
    parser.add_argument(
        "--sql-output",
        type=Path,
        default=None,
        help="Optional SQL output path (creates a readable .sql alongside .dump).",
    )
    parser.add_argument(
        "--with-sql",
        action="store_true",
        help="Also write a .sql file next to the .dump output.",
    )
    parser.add_argument(
        "--mode",
        choices=("docker", "local"),
        default="docker",
        help="Backup using docker exec or local pg_dump.",
    )
    parser.add_argument("--container", default="monassmat-db")
    parser.add_argument("--user", default="monassmat")
    parser.add_argument("--db", default="monassmat")
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Dump data only (no schema).",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Dump schema only (no data).",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL for local mode (defaults to DATABASE_URL or settings).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.sql_output is None and args.with_sql:
        args.sql_output = output_path.with_suffix(".sql")
    if args.sql_output is not None:
        args.sql_output.parent.mkdir(parents=True, exist_ok=True)

    if args.data_only and args.schema_only:
        raise SystemExit("Choose either --data-only or --schema-only, not both.")

    dump_args = []
    if args.data_only:
        dump_args.append("--data-only")
    elif args.schema_only:
        dump_args.append("--schema-only")

    if args.mode == "docker":
        cmd = [
            "docker",
            "exec",
            "-i",
            args.container,
            "pg_dump",
            "-U",
            args.user,
            "-Fc",
            args.db,
            *dump_args,
        ]
    else:
        db_url = args.db_url or os.environ.get("DATABASE_URL") or settings.database_url
        cmd = ["pg_dump", "-Fc", "-d", db_url, *dump_args]

    with output_path.open("wb") as handle:
        subprocess.run(cmd, check=True, stdout=handle)

    print(f"Backup written to {output_path}")

    if args.sql_output is not None:
        if args.mode == "docker":
            sql_cmd = [
                "docker",
                "exec",
                "-i",
                args.container,
                "pg_dump",
                "-U",
                args.user,
                "-Fp",
                args.db,
                *dump_args,
            ]
        else:
            db_url = (
                args.db_url or os.environ.get("DATABASE_URL") or settings.database_url
            )
            sql_cmd = ["pg_dump", "-Fp", "-d", db_url, *dump_args]

        with args.sql_output.open("w", encoding="utf-8") as handle:
            subprocess.run(sql_cmd, check=True, stdout=handle)
        print(f"SQL written to {args.sql_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
