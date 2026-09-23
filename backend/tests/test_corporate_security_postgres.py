"""Opt-in PostgreSQL concurrency proof. Creates/drops ONLY a UUID test database."""
import asyncio
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException, UploadFile
from tests.test_corporate_documents import pdf
from app.models.database import Base
from app.models.employee import Employee
from app.models.compliance_company import ComplianceCompany, CompanyPermission
from app.models.corporate_document import CorporateDocument
from app.models.compliance_audit import ComplianceAudit
from app.routers import corporate_documents as router
import io

pytestmark = pytest.mark.skipif(os.environ.get('CORPORATE_TEST_POSTGRES') != '1', reason='explicit disposable PostgreSQL opt-in required')


@pytest.fixture(scope='module')
def pg():
    name = 'corporate_security_' + uuid.uuid4().hex
    admin = create_engine('postgresql+psycopg2://hermes_release@127.0.0.1:55440/postgres', isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(f'postgresql+psycopg2://hermes_release@127.0.0.1:55440/{name}')
    try:
        Base.metadata.create_all(engine)
        print('DISPOSABLE DATABASE:', name)
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
        print('DROPPED:', name)


@pytest.fixture
def sessions(pg):
    Session = sessionmaker(bind=pg, autoflush=False)
    with Session() as db:
        db.query(ComplianceAudit).delete()
        db.query(CorporateDocument).delete()
        db.query(CompanyPermission).delete()
        db.query(ComplianceCompany).delete()
        db.query(Employee).delete()
        db.add(Employee(timestation_id='EDITOR', pin='1', name='Editor', role='admin'))
        db.add(ComplianceCompany(id=2, legal_name='Unchanged', ein='preserve', notes='unchanged'))
        db.flush()
        db.add(CompanyPermission(employee_id='EDITOR', company_id=2, can_edit=True))
        db.commit()
    return Session


def user():
    return {'timestation_id': 'EDITOR', 'name': 'Editor', 'role': 'admin'}


def change(db, kind):
    if kind == 'permission_delete':
        db.query(CompanyPermission).filter_by(employee_id='EDITOR').delete()
    elif kind == 'permission_update':
        db.query(CompanyPermission).filter_by(employee_id='EDITOR').update({'can_edit': False})
    elif kind == 'archive':
        db.query(ComplianceCompany).filter_by(id=2).update({'is_active': False})
    elif kind == 'role':
        db.query(Employee).filter_by(timestation_id='EDITOR').update({'role': 'employee'})
    else:
        db.query(Employee).filter_by(timestation_id='EDITOR').update({'login_enabled': False})


def snapshot(db):
    row = db.get(ComplianceCompany, 2)
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@pytest.mark.parametrize('kind', ['permission_delete', 'permission_update', 'archive', 'role', 'login'])
def test_actual_admin_rows_block_until_operation_commit(sessions, kind):
    import threading
    with sessions() as operation:
        before = snapshot(operation)
        router.access(operation, user(), 2, write=True)
        pid = []
        ready = threading.Event()
        def revoke():
            with sessions() as admin:
                pid.append(admin.execute(text('select pg_backend_pid()')).scalar_one())
                ready.set()
                change(admin, kind)
                admin.commit()
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(revoke)
            assert ready.wait(5)
            # Observe an actual server lock wait, not just thread scheduling.
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with sessions() as observer:
                    waiting = observer.execute(text("select wait_event_type = 'Lock' from pg_stat_activity where pid=:pid"), {'pid': pid[0]}).scalar()
                if waiting:
                    break
                time.sleep(.01)
            try:
                assert waiting, 'admin UPDATE/DELETE was not blocked by authorization row locks'
                assert not future.done()
                assert snapshot(operation) == before
                router.record_audit(operation, user(), 2, 'upload', new={'id': 1})
                operation.commit()
            finally:
                operation.rollback()
            future.result(timeout=5)
        print('LOCK CONTENTION VERIFIED:', kind)


@pytest.mark.parametrize('action', ['upload', 'replace'])
@pytest.mark.parametrize('kind', ['permission_delete', 'archive', 'role', 'login'])
def test_committed_validation_interleave_is_denied(sessions, monkeypatch, action, kind):
    with sessions() as db:
        row = CorporateDocument(company_id=2, document_type='EIN', original_file_name='old.pdf', content=pdf(), uploaded_by_user_id='EDITOR')
        db.add(row)
        db.commit()
        document_id = row.id
    original = router.validated_pdf
    async def interleave(*args):
        result = await original(*args)
        with sessions() as admin:
            change(admin, kind)
            admin.commit()
        return result
    monkeypatch.setattr(router, 'validated_pdf', interleave)
    with sessions() as db:
        file = UploadFile(io.BytesIO(pdf()), filename='new.pdf', headers={'content-type': 'application/pdf'})
        with pytest.raises(HTTPException) as error:
            if action == 'upload':
                asyncio.run(router.upload_document(2, file, 'EIN', '', user(), db))
            else:
                asyncio.run(router.replace_document(2, document_id, file, '', user(), db))
        assert error.value.status_code == 403
        db.rollback()
        assert db.query(CorporateDocument).count() == 1
        assert db.get(CorporateDocument, document_id).status == 'active'
        assert db.query(ComplianceAudit).count() == 0


@pytest.mark.parametrize('kind', ['permission_delete', 'permission_update', 'archive', 'role', 'login'])
def test_admin_wins_lock_wait_refreshes_authorization(sessions, kind):
    import threading
    ready = threading.Event()
    pid = []
    with sessions() as admin:
        change(admin, kind)  # Keep the revocation uncommitted and row locked.
        def operation():
            with sessions() as db:
                # Cache all authorization identities BEFORE waiting on locks.
                held = [db.query(Employee).one(), db.get(ComplianceCompany, 2), db.query(CompanyPermission).one()]
                pid.append(db.execute(text('select pg_backend_pid()')).scalar_one())
                ready.set()
                with pytest.raises(HTTPException) as error:
                    router.access(db, user(), 2, write=True)
                return error.value.status_code
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(operation)
            assert ready.wait(5)
            waiting = False
            deadline = time.monotonic() + 5
            try:
                while time.monotonic() < deadline:
                    with sessions() as observer:
                        waiting = observer.execute(text("select wait_event_type = 'Lock' from pg_stat_activity where pid=:pid"), {'pid': pid[0]}).scalar()
                    if waiting:
                        break
                    time.sleep(.01)
                assert waiting, 'operation must wait on the actual administrative row mutation'
            finally:
                admin.commit()
            assert future.result(timeout=5) == 403


@pytest.mark.parametrize('action', ['view', 'download', 'delete'])
@pytest.mark.parametrize('kind', ['permission_delete', 'role', 'login'])
def test_read_delete_recheck_current_authority(sessions, action, kind):
    with sessions() as db:
        row = CorporateDocument(company_id=2, document_type='EIN', original_file_name='old.pdf', content=pdf(), uploaded_by_user_id='EDITOR')
        db.add(row)
        db.commit()
        document_id = row.id
        stale_user = user()
        cached = [db.query(Employee).one(), db.query(CompanyPermission).one()]
        with sessions() as admin:
            change(admin, kind)
            admin.commit()
        with pytest.raises(HTTPException) as error:
            if action == 'delete':
                router.delete_document(2, document_id, stale_user, db)
            else:
                router.pdf_response(db, stale_user, 2, document_id, action)
        assert error.value.status_code == 403
        db.rollback()
        assert db.get(CorporateDocument, document_id).status == 'active'
        assert db.query(ComplianceAudit).count() == 0


def test_all_document_operations_preserve_all_company_columns(sessions):
    with sessions() as db:
        before = snapshot(db)
        def file():
            return UploadFile(io.BytesIO(pdf()), filename='record.pdf', headers={'content-type': 'application/pdf'})
        item = asyncio.run(router.upload_document(2, file(), 'EIN', '', user(), db))['document']
        router.pdf_response(db, user(), 2, item['id'], 'view')
        router.pdf_response(db, user(), 2, item['id'], 'download')
        replacement = asyncio.run(router.replace_document(2, item['id'], file(), '', user(), db))['document']
        router.delete_document(2, replacement['id'], user(), db)
        assert snapshot(db) == before
        assert db.query(ComplianceAudit).count() == 5


def test_cached_identities_are_refreshed_and_company_is_unchanged(sessions):
    with sessions() as db:
        before = snapshot(db)
        employee = db.query(Employee).one()
        permission = db.query(CompanyPermission).one()
        db.commit()
        # Hold actual identity objects and deliberately make them stale.
        db.refresh(employee)
        db.refresh(permission)
        with sessions() as admin:
            change(admin, 'permission_update')
            admin.commit()
        with pytest.raises(HTTPException) as error:
            router.access(db, user(), 2, write=True)
        assert error.value.status_code == 403
        assert permission.can_edit is False
        db.rollback()
        assert snapshot(db) == before
