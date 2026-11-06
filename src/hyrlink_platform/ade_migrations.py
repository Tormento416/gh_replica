"""Controlled PostgreSQL migration journal; never automatically adopts a schema.

Only reviewed, local SQL migrations are accepted. Each file must wrap its DDL in
BEGIN/COMMIT, with no nested transaction-control statements. The outer wrapper
is executed by this runner so the DDL and journal entry commit atomically.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from .contracts import PlatformError

_NAME = re.compile(r"ade_([0-9]{3})_[a-z][a-z0-9_]*\.sql\Z")
_WRAPPER = re.compile(r"\A(?P<comments>(?:\s*--[^\n]*\n)*)\s*BEGIN\s*;(?P<body>.*)\bCOMMIT\s*;\s*\Z", re.I | re.S)
_CONTROL = re.compile(r"(?im)^\s*(?:BEGIN|START\s+TRANSACTION|COMMIT|ROLLBACK|SAVEPOINT|RELEASE\s+SAVEPOINT|END)\b")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum: str
    body: str


def discover(directory):
    root = Path(directory)
    if not root.is_dir():
        raise PlatformError("migration_directory_missing")
    migrations = []
    for path in sorted(root.glob("*.sql")):
        match = _NAME.fullmatch(path.name)
        if not match or path.is_symlink():
            raise PlatformError("invalid_migration_name")
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise PlatformError("invalid_migration_encoding") from None
        wrapper = _WRAPPER.fullmatch(text)
        if not wrapper or not wrapper.group("body").strip() or _CONTROL.search(wrapper.group("body")):
            raise PlatformError("invalid_migration_transaction")
        migrations.append(Migration(int(match.group(1)), path.name, hashlib.sha256(raw).hexdigest(), wrapper.group("body")))
    if not migrations or [m.version for m in migrations] != list(range(1, len(migrations) + 1)):
        raise PlatformError("migration_sequence_invalid")
    return migrations


def _validate_applied(migrations, rows):
    if len(rows) > len(migrations):
        raise PlatformError("database_has_unknown_migrations")
    for row, migration in zip(rows, migrations):
        if row != (migration.version, migration.name, migration.checksum):
            raise PlatformError("migration_history_mismatch")
    return migrations[len(rows):]


def _history(connection):
    exists = connection.execute("SELECT to_regclass('public.ade_migration_journal') IS NOT NULL").fetchone()[0]
    if not exists:
        has_existing_schema = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname IN ('ade_core', 'ade_identity'))"
        ).fetchone()[0]
        if has_existing_schema:
            raise PlatformError("untracked_existing_schema")
        return None
    return connection.execute(
        "SELECT version, name, checksum FROM public.ade_migration_journal ORDER BY version"
    ).fetchall()


def plan(dsn, directory):
    migrations = discover(directory)
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as connection:
        rows = _history(connection)
        pending = _validate_applied(migrations, rows or [])
    return {"applied": len(rows or []), "pending": [m.name for m in pending]}


def apply(dsn, directory):
    """Apply each pending migration atomically under a single session lock."""
    migrations = discover(directory)
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as connection:
        locked = connection.execute("SELECT pg_try_advisory_lock(hashtext('ade_platform_migrations'))").fetchone()[0]
        if not locked:
            raise PlatformError("migration_lock_unavailable")
        try:
            rows = _history(connection)
            pending = _validate_applied(migrations, rows or [])
            if rows is None:
                # Refuse to take ownership of a pre-existing table or schema.
                connection.execute("""
                    CREATE TABLE public.ade_migration_journal (
                        version integer PRIMARY KEY,
                        name text NOT NULL UNIQUE,
                        checksum text NOT NULL,
                        applied_at timestamptz NOT NULL DEFAULT now()
                    )
                """)
            applied = []
            for migration in pending:
                with connection.transaction():
                    connection.execute("SET LOCAL lock_timeout = '5s'")
                    connection.execute("SET LOCAL statement_timeout = '60s'")
                    connection.execute(migration.body, prepare=False)
                    connection.execute(
                        "INSERT INTO public.ade_migration_journal (version, name, checksum) VALUES (%s, %s, %s)",
                        (migration.version, migration.name, migration.checksum),
                    )
                applied.append(migration.name)
            return {"applied": applied, "remaining": []}
        finally:
            connection.execute("SELECT pg_advisory_unlock(hashtext('ade_platform_migrations'))")
