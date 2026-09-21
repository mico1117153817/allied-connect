"""Offline migration fixtures. Never connect to configured application database."""
import hashlib
import sqlite3
import pytest
from sqlalchemy import create_engine, inspect
from app.routers.compliance import STATES


def test_startup_checks_before_any_schema_creation():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).parents[1] / 'app/main.py').read_text())
    lifespan = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'lifespan')
    calls = [ast.unparse(n) for statement in lifespan.body for n in ast.walk(statement) if isinstance(n, ast.Call)]
    guard = next((i for i, call in enumerate(calls) if call.startswith('assert_compliance_schema_ready(')), None)
    create = next(i for i, call in enumerate(calls) if call.startswith('Base.metadata.create_all('))
    assert guard is not None and guard < create


def test_backup_failure_and_parity_failure_leave_legacy_untouched(tmp_path, monkeypatch):
    from app.models import compliance_migration as migration
    engine = create_engine(f'sqlite:///{tmp_path / "fail.db"}')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE state_compliance (id INTEGER PRIMARY KEY, state VARCHAR UNIQUE NOT NULL)')
        conn.exec_driver_sql("INSERT INTO state_compliance VALUES (1, 'Colorado')")
    with pytest.raises(RuntimeError, match='migration'):
        migration.assert_compliance_schema_ready(engine)
    backup = tmp_path / 'existing.db'
    backup.write_bytes(b'do not overwrite')
    with pytest.raises(RuntimeError, match='overwrite'):
        migration.migrate_compliance(engine, backup)
    assert backup.read_bytes() == b'do not overwrite'
    original = migration._remove_global_unique
    def corrupt(conn):
        original(conn)
        conn.exec_driver_sql("UPDATE state_compliance SET state='CORRUPTION'")
    monkeypatch.setattr(migration, '_remove_global_unique', corrupt)
    with pytest.raises(RuntimeError, match='parity'):
        migration.migrate_compliance(engine, tmp_path / 'valid.db')
    with engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT state FROM state_compliance').scalar() == 'Colorado'
        assert 'company_id' not in {c['name'] for c in inspect(conn).get_columns('state_compliance')}
        assert not inspect(conn).has_table('compliance_migration_version')


@pytest.mark.parametrize('inline', [True, False])
def test_migration_backs_up_and_preserves_every_legacy_value(tmp_path, inline):
    from app.models import compliance_migration as migration
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    with engine.begin() as conn:
        conn.exec_driver_sql(f'CREATE TABLE state_compliance (id INTEGER PRIMARY KEY, state VARCHAR NOT NULL {"UNIQUE" if inline else ""}, notes TEXT, portal_password_encrypted TEXT, license_expiration DATE, unknown_legacy BLOB)')
        if not inline:
            conn.exec_driver_sql('CREATE UNIQUE INDEX ix_state_compliance_state ON state_compliance(state)')
        conn.exec_driver_sql('CREATE TABLE compliance_attachments (id INTEGER PRIMARY KEY, state VARCHAR, item_type VARCHAR, filename VARCHAR, content_type VARCHAR, content BLOB, uploaded_by VARCHAR, created_at TIMESTAMP)')
        for i, state in enumerate(STATES, 1):
            conn.exec_driver_sql('INSERT INTO state_compliance VALUES (?, ?, ?, ?, ?, ?)', (i, state, f'preserve {state}', 'opaque-encrypted', '2027-01-01', bytes([i])))
        conn.exec_driver_sql("INSERT INTO compliance_attachments VALUES (9, 'Colorado', 'license', 'history.pdf', 'application/pdf', ?, 'legacy', '2025-01-01')", (b'%PDF durable\x00\xff',))
    backup = tmp_path / 'backup.db'
    result = migration.migrate_compliance(engine, backup)
    assert result['verified'] is True and result['counts']['state_compliance'] == 51
    assert backup.exists()
    with sqlite3.connect(backup) as saved:
        assert 'company_id' not in {r[1] for r in saved.execute('PRAGMA table_info(state_compliance)')}
        old = saved.execute('SELECT * FROM state_compliance ORDER BY id').fetchall()
    with engine.begin() as conn:
        assert conn.exec_driver_sql('SELECT id,state,notes,portal_password_encrypted,license_expiration,unknown_legacy FROM state_compliance ORDER BY id').fetchall() == old
        assert conn.exec_driver_sql('SELECT content FROM compliance_attachments WHERE id=9').scalar() == b'%PDF durable\x00\xff'
        assert conn.exec_driver_sql('SELECT COUNT(*) FROM state_compliance WHERE company_id=1').scalar() == 51
        assert conn.exec_driver_sql('SELECT legacy_preserved FROM compliance_companies WHERE id=1').scalar()
        conn.exec_driver_sql("INSERT INTO compliance_companies (id,legal_name,is_active,legacy_preserved) VALUES (2,'B',1,0)")
        conn.exec_driver_sql("INSERT INTO state_compliance (state,company_id) VALUES ('Colorado',2)")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    assert migration.migrate_compliance(engine, backup)['already_current'] is True
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == digest
    migration.assert_compliance_schema_ready(engine)


def test_orphan_pdf_blocks_migration_and_rolls_back(tmp_path):
    from app.models import compliance_migration as migration
    engine = create_engine(f'sqlite:///{tmp_path / "orphan.db"}')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE state_compliance (id INTEGER PRIMARY KEY, state VARCHAR UNIQUE NOT NULL)')
        conn.exec_driver_sql("INSERT INTO state_compliance VALUES (1, 'Colorado')")
        conn.exec_driver_sql('CREATE TABLE compliance_attachments (id INTEGER PRIMARY KEY, state VARCHAR, content BLOB)')
        conn.exec_driver_sql("INSERT INTO compliance_attachments VALUES (1, 'Unknown State', X'25504446')")
    with pytest.raises(RuntimeError, match='orphan'):
        migration.migrate_compliance(engine, tmp_path / 'backup.db')
    assert 'company_id' not in {c['name'] for c in inspect(engine).get_columns('state_compliance')}


@pytest.mark.parametrize('corruption', ['unique', 'verification'])
def test_activation_rejects_missing_company_unique_or_verification(tmp_path, corruption):
    from app.models import compliance_migration as migration
    engine = create_engine(f'sqlite:///{tmp_path / "ready.db"}')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE state_compliance (id INTEGER PRIMARY KEY, state VARCHAR UNIQUE NOT NULL)')
        conn.exec_driver_sql("INSERT INTO state_compliance VALUES (1, 'Colorado')")
    migration.migrate_compliance(engine, tmp_path / 'backup.db')
    with engine.begin() as conn:
        conn.exec_driver_sql('DROP INDEX uq_compliance_company_state' if corruption == 'unique' else 'DELETE FROM compliance_migration_version')
    with pytest.raises(RuntimeError):
        migration.assert_compliance_schema_ready(engine)


def test_offline_cli_requires_backup_and_verifies_fixture(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    database = tmp_path / 'cli.db'
    engine = create_engine(f'sqlite:///{database}')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE state_compliance (id INTEGER PRIMARY KEY, state VARCHAR UNIQUE NOT NULL)')
        conn.exec_driver_sql("INSERT INTO state_compliance VALUES (1, 'Colorado')")
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{database.as_posix()}'}
    command = [sys.executable, '-m', 'app.models.compliance_migration']
    cwd = str(Path(__file__).parents[1])
    missing = subprocess.run(command, env=env, cwd=cwd, capture_output=True, text=True)
    assert missing.returncode == 2
    result = subprocess.run(command + ['--backup', str(tmp_path / 'backup.db')], env=env, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['verified'] is True
