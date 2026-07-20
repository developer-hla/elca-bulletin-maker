"""Database backup to the artifact store.

Dumps ``$DATABASE_URL`` with ``pg_dump`` (custom format, ``-Fc``) and uploads
it through the existing :class:`~bulletin_maker.web.artifacts.ArtifactStore`
under ``backups/<UTC timestamp>.dump``, then prunes all but the newest
``$BULLETIN_BACKUP_KEEP`` (default 14).

Backups are deliberately NOT recorded in the ``artifacts`` table: a database
backup must not depend on the database. Listing and pruning go through the
store backend directly.

Run from cron::

    python -m bulletin_maker.web.backup

``--list`` prints existing backups. The process exits non-zero on any failure
so a scheduler notices.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.web.artifacts import ArtifactStore, StoredObject, get_store
from bulletin_maker.web.db import database_url

BACKUP_PREFIX = "backups/"
BACKUP_SUFFIX = ".dump"
DEFAULT_KEEP = 14
PG_DUMP_FALLBACK = "/opt/homebrew/opt/postgresql@16/bin/pg_dump"
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


class BackupError(BulletinError):
    """A backup could not be created, listed, or pruned."""


def _resolve_pg_dump() -> str:
    """Locate pg_dump: $PG_DUMP, then PATH, then the Homebrew install."""
    configured = os.environ.get("PG_DUMP")
    if configured:
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        if Path(configured).is_file():
            return configured
    on_path = shutil.which("pg_dump")
    if on_path:
        return on_path
    if Path(PG_DUMP_FALLBACK).is_file():
        return PG_DUMP_FALLBACK
    raise BackupError(
        "pg_dump not found. Set $PG_DUMP to its full path, put it on PATH, "
        f"or install it at {PG_DUMP_FALLBACK}.")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def _backup_key(timestamp: str) -> str:
    return f"{BACKUP_PREFIX}{timestamp}{BACKUP_SUFFIX}"


def create_backup(store: Optional[ArtifactStore] = None) -> str:
    """Dump the database and upload it; return the stored object key."""
    store = store or get_store()
    pg_dump = _resolve_pg_dump()
    handle = tempfile.NamedTemporaryFile(suffix=BACKUP_SUFFIX, delete=False)
    handle.close()
    dump_path = handle.name
    try:
        command = [pg_dump, "-Fc", "--file", dump_path, database_url()]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise BackupError(
                f"pg_dump exited {result.returncode}: {result.stderr.strip()}")
        key = _backup_key(_timestamp())
        store.put(key, dump_path)
        return key
    finally:
        Path(dump_path).unlink(missing_ok=True)


def list_backups(store: Optional[ArtifactStore] = None) -> List[StoredObject]:
    """All backups, oldest first (timestamped keys sort chronologically)."""
    store = store or get_store()
    backups = [obj for obj in store.list(BACKUP_PREFIX)
               if obj.key.endswith(BACKUP_SUFFIX)]
    return sorted(backups, key=lambda obj: obj.key)


def keys_to_prune(keys: List[str], keep: int) -> List[str]:
    """The oldest keys beyond the newest ``keep`` — the ones to delete."""
    if keep < 0:
        raise BackupError("keep count cannot be negative.")
    ordered = sorted(keys)
    if len(ordered) <= keep:
        return []
    return ordered[:len(ordered) - keep]


def prune_backups(store: Optional[ArtifactStore] = None,
                  keep: int = DEFAULT_KEEP) -> List[str]:
    """Delete all but the newest ``keep`` backups; return the deleted keys."""
    store = store or get_store()
    keys = [obj.key for obj in list_backups(store)]
    doomed = keys_to_prune(keys, keep)
    for key in doomed:
        store.delete(key)
    return doomed


def _keep_from_env() -> int:
    raw = os.environ.get("BULLETIN_BACKUP_KEEP")
    if not raw:
        return DEFAULT_KEEP
    try:
        return int(raw)
    except ValueError:
        raise BackupError(f"BULLETIN_BACKUP_KEEP must be an integer, got {raw!r}.")


def _print_listing(store: ArtifactStore) -> None:
    backups = list_backups(store)
    if not backups:
        print("No backups found.")
        return
    for obj in backups:
        size_mb = obj.size / (1024 * 1024)
        stamp = obj.modified.astimezone(timezone.utc).isoformat()
        print(f"{obj.key}\t{size_mb:.2f} MB\t{stamp}")


def _run_backup() -> None:
    store = get_store()
    keep = _keep_from_env()
    key = create_backup(store)
    pruned = prune_backups(store, keep)
    print(f"Backup stored at {key}; pruned {len(pruned)} old backup(s), "
          f"keeping {keep}.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bulletin_maker.web.backup",
        description="Back up the database to the artifact store.")
    parser.add_argument(
        "--list", action="store_true",
        help="List existing backups and exit.")
    args = parser.parse_args(argv)
    try:
        if args.list:
            _print_listing(get_store())
            return 0
        _run_backup()
        return 0
    except Exception as error:
        print(f"backup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
