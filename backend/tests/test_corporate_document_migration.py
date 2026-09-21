"""Additive migration contract on populated schemas, with actual constraints."""
import importlib.util
import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.database import Base
from app.models.employee import Employee
from app.models.compliance_company import ComplianceCompany
from app.models.corporate_document import CorporateDocument


def test_additive_idempotent_migration_preserves_every_existing_row():
    assert importlib.util.find_spec('app.models.corporate_document_migration'), 'Explicit additive migration is required'
    from app.models.corporate_document_migration import ensure_corporate_document_schema
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != 'corporate_documents'])
    with Session(engine) as db:
        db.add(Employee(timestation_id='U', name='Test', pin='1'))
        db.add(ComplianceCompany(id=7, legal_name='Preserved', ein='unchanged'))
        db.flush()
        from app.models.state_compliance import StateCompliance
        from app.models.compliance_attachment import ComplianceAttachment
        from app.models.compliance_audit import ComplianceAudit
        db.add(StateCompliance(company_id=7, state='Alabama', license_number='preserve-license'))
        db.add(ComplianceAttachment(company_id=7, state='Alabama', item_type='license', filename='legacy.pdf', content=b'legacy-bytes'))
        db.add(ComplianceAudit(company_id=7, user_id='U', field='legacy', new_value='preserve-audit'))
        db.commit()
    def snapshot():
        with engine.connect() as c:
            return {name: c.exec_driver_sql('SELECT * FROM "' + name + '"').all()
                    for name in inspect(engine).get_table_names() if name != 'corporate_documents'}
    before = snapshot()
    ensure_corporate_document_schema(engine)
    ensure_corporate_document_schema(engine)
    assert snapshot() == before
    values = dict(company_id=7, document_type='EIN', original_file_name='x.pdf', uploaded_by_user_id='U', content=b'%PDF-test')
    with Session(engine) as db:
        row = CorporateDocument(**values)
        db.add(row)
        db.commit()
        key = row.storage_key
    ensure_corporate_document_schema(engine)
    with Session(engine) as db:
        assert db.query(CorporateDocument).count() == 1
        assert db.query(CorporateDocument).one().storage_key == key
    for override in ({'company_id': 999}, {'uploaded_by_user_id': 'missing'}, {'document_type': 'Not a category'},
                     {'status': 'invalid'}, {'storage_key': key}, {'replaced_document_id': 999}, {'notes': 'x' * 4001}):
        with Session(engine) as db:
            db.add(CorporateDocument(**{**values, **override}))
            with pytest.raises(IntegrityError):
                db.commit()
    assert snapshot() == before


def test_startup_explicit_migration_creates_table_not_create_all(monkeypatch):
    import asyncio
    import app.main as main
    from sqlalchemy.orm import sessionmaker
    engine = create_engine('sqlite://')
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'SessionLocal', sessionmaker(bind=engine))
    monkeypatch.setattr(main, 'init_defaults', lambda db: None)
    async def noop():
        return None
    monkeypatch.setattr(main, 'bootstrap_managers', noop)
    class Scheduler:
        def shutdown(self, wait=False):
            pass
    monkeypatch.setattr(main, 'start_scheduler', lambda: Scheduler())
    original = main.ensure_corporate_document_schema
    calls = []
    def migrate(engine):
        calls.append('corporate_documents' in inspect(engine).get_table_names())
        original(engine)
    monkeypatch.setattr(main, 'ensure_corporate_document_schema', migrate)
    async def start():
        async with main.lifespan(main.app):
            assert 'corporate_documents' in inspect(engine).get_table_names()
    asyncio.run(start())
    assert calls == [False], 'Explicit migration, not generic create_all, must create corporate_documents'


def test_main_registers_router_and_runs_explicit_migration_after_guard():
    import ast
    from pathlib import Path
    source = Path('app/main.py').read_text()
    tree = ast.parse(source)
    lifespan = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'lifespan')
    calls = [ast.unparse(n.func) for n in ast.walk(lifespan) if isinstance(n, ast.Call)]
    assert 'ensure_corporate_document_schema' in calls
    assert calls.index('assert_compliance_schema_ready') < calls.index('ensure_corporate_document_schema')
    from app.main import app
    assert any(route.path == '/api/compliance/companies/{company_id}/corporate-documents' for route in app.routes)
    assert 'corporate_documents' in Base.metadata.tables
