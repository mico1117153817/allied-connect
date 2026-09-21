"""Explicit offline migration. Startup only validates; it never migrates a live legacy DB.

SQLite backup uses the database backup API. PostgreSQL requires pg_dump and
pg_restore on PATH. Run with all application writers stopped. Every legacy
column, row ID, encrypted value and PDF byte is hashed before/after, in one
DDL transaction. A missing/incomplete backup or parity failure aborts activation.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

from sqlalchemy import Column, MetaData, Table, UniqueConstraint, inspect, text
from sqlalchemy.schema import CreateColumn
from app.models.database import Base
from app.models.compliance_company import ComplianceCompany, CompanyPermission, CompanyLogo
from app.models.compliance_audit import ComplianceAudit
from app.models.compliance_attachment import ComplianceAttachment
from app.models.state_compliance import StateCompliance, SCHEMA_UPGRADE_COLUMNS

VERSION = 'multicompany-v1'
TABLES = ('state_compliance', 'compliance_attachments')


def _snapshot(conn, columns=None):
    inspector = inspect(conn)
    columns = columns or {t: [c['name'] for c in inspector.get_columns(t)] for t in TABLES if inspector.has_table(t)}
    result = {}
    quote = conn.dialect.identifier_preparer.quote
    for table, names in columns.items():
        rows = conn.exec_driver_sql(f'SELECT {",".join(quote(n) for n in names)} FROM {quote(table)} ORDER BY id').fetchall()
        def encode(v):
            if isinstance(v, (bytes, memoryview)):
                return {'bytes': bytes(v).hex()}
            return str(v) if v is not None else None
        payload = json.dumps([[encode(v) for v in row] for row in rows], separators=(',', ':')).encode()
        result[table] = {'count': len(rows), 'sha256': hashlib.sha256(payload).hexdigest()}
    return columns, result


def _is_current(conn):
    i = inspect(conn)
    return i.has_table('compliance_migration_version') and conn.exec_driver_sql(
        'SELECT version FROM compliance_migration_version WHERE version = ' + "'" + VERSION + "'").first() is not None


def _validate_relationships(conn):
    for table in TABLES:
        if conn.exec_driver_sql(f'SELECT COUNT(*) FROM {table} r LEFT JOIN compliance_companies c ON c.id=r.company_id WHERE c.id IS NULL').scalar():
            raise RuntimeError('Unscoped or orphan company records; refusing activation')
    if conn.exec_driver_sql('SELECT COUNT(*) FROM compliance_attachments a LEFT JOIN state_compliance s ON s.company_id=a.company_id AND s.state=a.state WHERE s.id IS NULL').scalar():
        raise RuntimeError('An orphan compliance document has no company/jurisdiction; refusing activation')


def assert_compliance_schema_ready(engine):
    with engine.connect() as conn:
        i = inspect(conn)
        if not i.has_table('state_compliance'):
            return  # genuinely fresh database
        for model in (StateCompliance, ComplianceAttachment, ComplianceCompany, CompanyPermission, CompanyLogo, ComplianceAudit):
            table = model.__tablename__
            if not i.has_table(table) or not {c.name for c in model.__table__.columns} <= {c['name'] for c in i.get_columns(table)}:
                raise RuntimeError('Compliance offline backup/migration required before startup')
        uniques = i.get_unique_constraints('state_compliance') + i.get_indexes('state_compliance')
        if any(u.get('column_names') == ['state'] and u.get('unique', True) for u in uniques):
            raise RuntimeError('Legacy global state uniqueness remains; migration required')
        if not any(set(u.get('column_names') or []) == {'company_id', 'state'} and u.get('unique', True) for u in uniques):
            raise RuntimeError('Company/jurisdiction uniqueness missing; refusing activation')
        _validate_relationships(conn)
        preserved = conn.exec_driver_sql('SELECT legacy_preserved FROM compliance_companies WHERE id=1').scalar()
        if preserved and not _is_current(conn):
            raise RuntimeError('Legacy migration verification missing; refusing activation')


def _backup(engine, path):
    path = Path(path)
    if path.exists():
        raise RuntimeError('Backup destination exists; refusing to overwrite')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation plus restrictive permissions: backup includes credentials.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    if engine.dialect.name == 'sqlite':
        with engine.connect() as conn, sqlite3.connect(path) as target:
            conn.connection.driver_connection.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed')
    elif engine.dialect.name == 'postgresql':
        url = engine.url
        env = {**os.environ, 'PGPASSWORD': url.password or ''}
        args = ['pg_dump', '--format=custom', '--file', str(path), '--host', url.host or 'localhost',
                '--port', str(url.port or 5432), '--username', url.username or '', '--dbname', url.database or '']
        try:
            subprocess.run(args, env=env, check=True, capture_output=True)
            subprocess.run(['pg_restore', '--list', str(path)], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError('PostgreSQL backup verification failed; no schema changes made') from exc
    else:
        raise RuntimeError('Unsupported database dialect')
    if path.stat().st_size == 0:
        raise RuntimeError('Empty backup')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_columns(conn, model):
    i = inspect(conn)
    table = model.__tablename__
    existing = {c['name'] for c in i.get_columns(table)}
    for col in model.__table__.columns:
        if col.name in existing:
            continue
        # Add only: legacy column types, defaults, values and unknown columns survive.
        if col.name == 'company_id':
            ddl = 'company_id INTEGER NOT NULL DEFAULT 1 REFERENCES compliance_companies(id)'
        elif col.name in SCHEMA_UPGRADE_COLUMNS:
            ddl = f'{col.name} {SCHEMA_UPGRADE_COLUMNS[col.name]}'
        else:
            copied = Column(col.name, col.type, nullable=True)
            ddl = str(CreateColumn(copied).compile(dialect=conn.dialect))
            if not col.nullable and col.default is not None and col.default.is_scalar:
                default = col.default.arg
                literal = str(default).lower() if isinstance(default, bool) else "'" + str(default).replace("'", "''") + "'"
                ddl += f' NOT NULL DEFAULT {literal}'
        conn.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {ddl}')


def _remove_global_unique(conn):
    i = inspect(conn)
    quote = conn.dialect.identifier_preparer.quote
    constraints = [u for u in i.get_unique_constraints('state_compliance') if u['column_names'] == ['state']]
    indexes = [u for u in i.get_indexes('state_compliance') if u.get('unique') and u['column_names'] == ['state'] and not u.get('duplicates_constraint')]
    if conn.dialect.name == 'sqlite' and constraints:
        # Reflect every legacy column, including ones this application does not know.
        # Explicit transaction + full database backup protects the table-copy DDL.
        triggers = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='state_compliance'").fetchall()
        if triggers:
            raise RuntimeError('Custom SQLite triggers require manual reviewed migration')
        metadata = MetaData()
        original = Table('state_compliance', metadata, autoload_with=conn)
        clone_metadata = MetaData()
        for other in metadata.tables.values():
            if other.name != 'state_compliance':
                other.to_metadata(clone_metadata)
        clone = original.to_metadata(clone_metadata, name='_compliance_migration_states')
        for constraint in list(clone.constraints):
            if isinstance(constraint, UniqueConstraint) and [c.name for c in constraint.columns] == ['state']:
                clone.constraints.remove(constraint)
        # Recreate indexes after dropping old table, preventing name collisions.
        old_indexes = list(clone.indexes)
        clone.indexes.clear()
        clone.create(conn)
        names = ','.join(quote(c.name) for c in original.columns)
        conn.exec_driver_sql(f'INSERT INTO _compliance_migration_states ({names}) SELECT {names} FROM state_compliance')
        conn.exec_driver_sql('DROP TABLE state_compliance')
        conn.exec_driver_sql('ALTER TABLE _compliance_migration_states RENAME TO state_compliance')
        for index in old_indexes:
            if index.unique and [c.name for c in index.columns] == ['state']:
                continue
            cols = ','.join(quote(c.name) for c in index.columns)
            conn.exec_driver_sql(f'CREATE {"UNIQUE " if index.unique else ""}INDEX {quote(index.name)} ON state_compliance ({cols})')
    else:
        for constraint in constraints:
            conn.exec_driver_sql(f'ALTER TABLE state_compliance DROP CONSTRAINT {quote(constraint["name"])}')
        for index in indexes:
            conn.exec_driver_sql(f'DROP INDEX {quote(index["name"])}')
    conn.exec_driver_sql('CREATE UNIQUE INDEX uq_compliance_company_state ON state_compliance(company_id,state)')


def migrate_compliance(engine, backup_path):
    with engine.connect() as conn:
        if _is_current(conn):
            assert_compliance_schema_ready(engine)
            return {'already_current': True, 'verified': True}
        if not inspect(conn).has_table('state_compliance'):
            raise RuntimeError('No legacy compliance register to migrate')
        columns, before = _snapshot(conn)
    backup_hash = _backup(engine, backup_path)  # MUST precede all schema writes
    with engine.connect() as conn:
        if engine.dialect.name == 'sqlite':
            conn.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            conn.begin()
            conn.exec_driver_sql('LOCK TABLE state_compliance IN ACCESS EXCLUSIVE MODE')
            if inspect(conn).has_table('compliance_attachments'):
                conn.exec_driver_sql('LOCK TABLE compliance_attachments IN ACCESS EXCLUSIVE MODE')
        try:
            if _snapshot(conn, columns)[1] != before:
                raise RuntimeError('Legacy data changed during backup; stop writers and retry')
            for model in (ComplianceCompany, CompanyPermission, CompanyLogo, ComplianceAudit):
                model.__table__.create(conn, checkfirst=True)
            if conn.exec_driver_sql('SELECT COUNT(*) FROM compliance_companies').scalar():
                raise RuntimeError('Partial/ambiguous migration detected; refusing to assign legacy rows')
            conn.execute(ComplianceCompany.__table__.insert().values(id=1, legal_name='Allied Alliance Group Inc.', is_active=True, legacy_preserved=True))
            employee_schema = inspect(conn)
            if employee_schema.has_table('employees') and {'role', 'timestation_id'} <= {c['name'] for c in employee_schema.get_columns('employees')}:
                conn.execute(text('INSERT INTO compliance_company_permissions (employee_id, company_id, can_edit) '
                                  "SELECT e.timestation_id, 1, TRUE FROM employees e WHERE e.role = 'admin' "
                                  'AND NOT EXISTS (SELECT 1 FROM compliance_company_permissions p WHERE p.employee_id=e.timestation_id AND p.company_id=1)'))
            for model in (StateCompliance, ComplianceAttachment):
                if inspect(conn).has_table(model.__tablename__):
                    _add_columns(conn, model)
                else:
                    model.__table__.create(conn)
            _remove_global_unique(conn)
            _validate_relationships(conn)
            after = _snapshot(conn, columns)[1]
            if before != after:
                raise RuntimeError('Legacy column/count/hash/PDF parity failed; transaction rolled back')
            if engine.dialect.name == 'postgresql':
                conn.exec_driver_sql("SELECT setval(pg_get_serial_sequence('compliance_companies','id'), (SELECT MAX(id) FROM compliance_companies))")
            conn.exec_driver_sql('CREATE TABLE compliance_migration_version (version VARCHAR PRIMARY KEY, backup_sha256 VARCHAR NOT NULL, parity_json TEXT NOT NULL)')
            conn.execute(text('INSERT INTO compliance_migration_version VALUES (:version,:backup,:parity)'), {'version': VERSION, 'backup': backup_hash, 'parity': json.dumps(before)})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    assert_compliance_schema_ready(engine)
    return {'verified': True, 'already_current': False, 'backup_sha256': backup_hash,
            'counts': {t: v['count'] for t, v in before.items()}, 'parity': before}


def main():
    import argparse
    from app.models.database import engine
    parser = argparse.ArgumentParser(description='Offline multi-company migration. Stop all application writers first.')
    parser.add_argument('--backup', required=True, help='New durable backup path; existing files are never overwritten')
    args = parser.parse_args()
    print(json.dumps(migrate_compliance(engine, args.backup), sort_keys=True))


if __name__ == '__main__':
    main()
