"""Durable artifact storage for generated bulletin PDFs.

Generated PDFs are uploaded to an object store so downloads survive a
server restart, and a row is recorded in the ``artifacts`` table linking
a job's document to its stored object. Objects expire after a TTL and are
reclaimed by :func:`purge_expired_artifacts`.

Two backends, chosen by the ``ARTIFACT_STORE`` env var:

* ``local`` (default) — files under ``BULLETIN_ARTIFACT_DIR``
  (default ``~/.bulletin-maker/artifacts``).
* ``s3`` — any S3-compatible service (AWS S3, Cloudflare R2) via boto3,
  configured with ``S3_ENDPOINT_URL``, ``S3_BUCKET``,
  ``S3_ACCESS_KEY_ID`` and ``S3_SECRET_ACCESS_KEY``.

Object keys are laid out as ``{church_id}/{job_id}/{doc_key}/{filename}``.

Run ``python -m bulletin_maker.web.artifacts --purge`` (e.g. from cron) to
reclaim expired objects out of band.
"""

from __future__ import annotations

import argparse
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.web import db

ARTIFACT_TTL_DAYS = 7
STREAM_CHUNK_BYTES = 64 * 1024
DEFAULT_LOCAL_DIR = Path.home() / ".bulletin-maker" / "artifacts"

Source = Union[str, Path, bytes]


# ── Store abstraction ────────────────────────────────────────────────

class ArtifactStore(ABC):
    """Backend-agnostic object store for generated files."""

    @abstractmethod
    def put(self, object_key: str, source: Source) -> int:
        """Store ``source`` (a file path or raw bytes); return byte count."""

    @abstractmethod
    def open_stream(self, object_key: str):
        """Return a readable binary stream; the caller must close it."""

    @abstractmethod
    def delete(self, object_key: str) -> None:
        """Delete the object; a missing object is not an error."""

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        """Whether the object is present."""


def _as_bytes(source: Source) -> bytes:
    if isinstance(source, bytes):
        return source
    return Path(source).read_bytes()


class LocalArtifactStore(ArtifactStore):
    """Files under a base directory, keyed by object key path."""

    def __init__(self, base_dir: Path) -> None:
        self._base = Path(base_dir)

    def _path(self, object_key: str) -> Path:
        return self._base / object_key

    def put(self, object_key: str, source: Source) -> int:
        data = _as_bytes(source)
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return len(data)

    def open_stream(self, object_key: str):
        return self._path(object_key).open("rb")

    def delete(self, object_key: str) -> None:
        self._path(object_key).unlink(missing_ok=True)

    def exists(self, object_key: str) -> bool:
        return self._path(object_key).exists()


class S3ArtifactStore(ArtifactStore):
    """S3-compatible object store (AWS S3, Cloudflare R2) via boto3."""

    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, object_key: str, source: Source) -> int:
        data = _as_bytes(source)
        self._client.put_object(Bucket=self._bucket, Key=object_key, Body=data)
        return len(data)

    def open_stream(self, object_key: str):
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        return response["Body"]

    def delete(self, object_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=object_key)

    def exists(self, object_key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise


# ── Backend selection ────────────────────────────────────────────────

def _local_dir() -> Path:
    configured = os.environ.get("BULLETIN_ARTIFACT_DIR")
    return Path(configured) if configured else DEFAULT_LOCAL_DIR


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise BulletinError(
            f"ARTIFACT_STORE=s3 requires {name} to be set.")
    return value


def _build_s3_store() -> S3ArtifactStore:
    import boto3
    bucket = _require_env("S3_BUCKET")
    client = boto3.client(
        "s3",
        endpoint_url=_require_env("S3_ENDPOINT_URL"),
        aws_access_key_id=_require_env("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=_require_env("S3_SECRET_ACCESS_KEY"),
    )
    return S3ArtifactStore(client, bucket)


def get_store() -> ArtifactStore:
    backend = os.environ.get("ARTIFACT_STORE", "local")
    if backend == "local":
        return LocalArtifactStore(_local_dir())
    if backend == "s3":
        return _build_s3_store()
    raise BulletinError(
        f"Unknown ARTIFACT_STORE {backend!r}; expected 'local' or 's3'.")


# ── Streaming helper ─────────────────────────────────────────────────

def iter_object(object_key: str, chunk_size: int = STREAM_CHUNK_BYTES):
    """Yield an object's bytes in chunks, closing the stream when done."""
    stream = get_store().open_stream(object_key)
    try:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                return
            yield chunk
    finally:
        stream.close()


def read_object(object_key: str) -> bytes:
    stream = get_store().open_stream(object_key)
    try:
        return stream.read()
    finally:
        stream.close()


# ── artifacts table ──────────────────────────────────────────────────

def default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=ARTIFACT_TTL_DAYS)


def record_artifact(job_id: str, doc_key: str, filename: str,
                    object_key: str, num_bytes: int,
                    expires_at: datetime) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO artifacts (job_id, doc_key, filename, object_key,"
            " bytes, expires_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (job_id, doc_key, filename, object_key, num_bytes, expires_at),
        )


def artifacts_for_job(job_id: str) -> list:
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM artifacts WHERE job_id = %s ORDER BY id",
            (job_id,)).fetchall()


def artifact_for_doc(job_id: str, doc_key: str) -> Optional[dict]:
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM artifacts WHERE job_id = %s AND doc_key = %s"
            " ORDER BY id DESC LIMIT 1",
            (job_id, doc_key)).fetchone()


def purge_expired_artifacts() -> int:
    """Delete expired store objects and their rows; return the row count."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, object_key FROM artifacts"
            " WHERE expires_at IS NOT NULL AND expires_at < now()").fetchall()
    if not rows:
        return 0
    store = get_store()
    for row in rows:
        store.delete(row["object_key"])
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM artifacts WHERE id = ANY(%s)",
            ([row["id"] for row in rows],))
    return len(rows)


def _main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m bulletin_maker.web.artifacts",
        description="Bulletin Maker artifact store maintenance.")
    parser.add_argument(
        "--purge", action="store_true",
        help="Delete expired artifact objects and rows.")
    args = parser.parse_args()
    if not args.purge:
        parser.error("nothing to do; pass --purge")
    count = purge_expired_artifacts()
    print(f"Purged {count} expired artifact(s).")


if __name__ == "__main__":
    _main()
