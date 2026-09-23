"""Real JWT/HTTP corporate document contract; isolated SQLite, no production env."""
import io
import importlib.util
import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.jwt import create_access_token
from app.models.database import Base, get_db
from app.models.employee import Employee
from app.models.compliance_company import ComplianceCompany, CompanyPermission
from app.models.compliance_audit import ComplianceAudit
from app.routers import compliance

CATEGORIES = ['EIN', 'Articles of Incorporation', 'Operating Agreement', 'Bylaws',
              'Certificate of Good Standing', 'Other Corporate Document']
PREFIX = '/api/compliance/companies/{}/corporate-documents'


def pdf(encrypted=False):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if encrypted:
        writer.encrypt('test-only')
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.fixture
def harness():
    app = FastAPI()
    app.include_router(compliance.router)
    if importlib.util.find_spec('app.routers.corporate_documents'):
        from app.routers.corporate_documents import router
        app.include_router(router)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        db.add_all([Employee(timestation_id=key, name=key, pin=str(index), role=role)
                    for index, (key, role) in enumerate([('ROOT', 'super_admin'), ('EDIT', 'admin'),
                        ('READ', 'admin'), ('OTHER', 'admin'), ('MGR', 'manager'), ('EMP', 'employee')])])
        db.add_all([ComplianceCompany(id=2, legal_name='Same name', ein='preserve-A'),
                    ComplianceCompany(id=3, legal_name='Same name', ein='preserve-B')])
        db.flush()
        db.add_all([CompanyPermission(employee_id='EDIT', company_id=2, can_edit=True),
                    CompanyPermission(employee_id='READ', company_id=2, can_edit=False),
                    CompanyPermission(employee_id='OTHER', company_id=3, can_edit=True)])
        db.commit()
    def database():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = database
    client = TestClient(app, raise_server_exceptions=False)
    def login(who='ROOT'):
        client.headers['Authorization'] = 'Bearer ' + create_access_token({'sub': who, 'role': 'super_admin'})
    login()
    yield client, Session, login
    engine.dispose()


def upload(client, company=2, category='EIN', content=None, filename='record.pdf', mime='application/pdf', notes='Filed'):
    return client.post(PREFIX.format(company), data={'document_type': category, 'notes': notes},
                       files={'file': (filename, pdf() if content is None else content, mime)})


def replace(client, company, document_id, content=None, notes='New version'):
    return client.post(PREFIX.format(company) + f'/{document_id}/replace', data={'notes': notes},
                       files={'file': ('updated.pdf', pdf() + b'\n%new' if content is None else content, 'application/pdf')})


@pytest.mark.parametrize('who,read,write', [('ROOT', True, True), ('EDIT', True, True), ('READ', True, False),
                                                 ('OTHER', False, False), ('MGR', False, False), ('EMP', False, False)])
def test_real_jwt_role_and_company_permissions(harness, who, read, write):
    client, Session, login = harness
    item = upload(client).json()['document']
    login(who)
    assert client.get(PREFIX.format(2)).status_code == (200 if read else 403)
    if read:
        assert client.get(PREFIX.format(2)).json()['can_edit'] is write
    assert client.get(item['view_url']).status_code == (200 if read else 403)
    assert client.get(item['download_url']).status_code == (200 if read else 403)
    assert upload(client).status_code == (201 if write else 403)
    assert replace(client, 2, item['id']).status_code == (201 if write else 403)
    assert client.delete(PREFIX.format(2) + f"/{item['id']}").status_code == (204 if write else 403)


def test_paired_cross_company_scope_even_for_super_admin(harness):
    client, Session, login = harness
    a = upload(client, 2).json()['document']
    b = upload(client, 3).json()['document']
    for who, own, other, item in [('EDIT', 2, 3, a), ('OTHER', 3, 2, b)]:
        login(who)
        assert client.get(PREFIX.format(own)).status_code == 200
        assert upload(client, own).status_code == 201
        assert client.get(PREFIX.format(other)).status_code == 403
        assert upload(client, other).status_code == 403
        foreign = b if own == 2 else a
        for action in ('view', 'download'):
            assert client.get(foreign[action + '_url']).status_code == 403
            assert client.get(PREFIX.format(own) + f"/{foreign['id']}/{action}").status_code == 404
        assert replace(client, own, foreign['id']).status_code == 404
        assert client.delete(PREFIX.format(own) + f"/{foreign['id']}").status_code == 404
    login('ROOT')
    for company, item in [(2, b), (3, a)]:
        for action in ('view', 'download'):
            assert client.get(PREFIX.format(company) + f"/{item['id']}/{action}").status_code == 404
        assert replace(client, company, item['id']).status_code == 404
        assert client.delete(PREFIX.format(company) + f"/{item['id']}").status_code == 404
    assert [d['id'] for d in client.get(PREFIX.format(2)).json()['documents']].count(b['id']) == 0


@pytest.mark.parametrize('restriction', ['anonymous', 'disabled', 'revoked', 'archived'])
def test_permission_changes_take_effect_on_existing_jwt(harness, restriction):
    client, Session, login = harness
    item = upload(client).json()['document']
    login('EDIT')
    with Session() as db:
        if restriction == 'disabled':
            db.query(Employee).filter_by(timestation_id='EDIT').one().login_enabled = False
        if restriction == 'revoked':
            db.query(CompanyPermission).filter_by(employee_id='EDIT').delete()
        if restriction == 'archived':
            db.get(ComplianceCompany, 2).is_active = False
        db.commit()
    if restriction == 'anonymous':
        client.headers.pop('Authorization')
    read_status = 200 if restriction == 'archived' else 401 if restriction == 'anonymous' else 403
    write_status = 401 if restriction == 'anonymous' else 403
    assert client.get(PREFIX.format(2)).status_code == read_status
    for action in ('view', 'download'):
        assert client.get(item[action + '_url']).status_code == read_status
    assert upload(client).status_code == write_status
    assert replace(client, 2, item['id']).status_code == write_status
    assert client.delete(PREFIX.format(2) + f"/{item['id']}").status_code == write_status
    if restriction == 'archived':
        login('ROOT')
        assert client.get(PREFIX.format(2)).json()['can_edit'] is False
        assert upload(client).status_code == 403
        assert replace(client, 2, item['id']).status_code == 403
        assert client.delete(PREFIX.format(2) + f"/{item['id']}").status_code == 403


def test_missing_ids_never_create_default_company(harness):
    client, Session, _ = harness
    for company in (1, 999999):
        assert client.get(PREFIX.format(company)).status_code == 404
        assert upload(client, company).status_code == 404
        for action in ('view', 'download'):
            assert client.get(PREFIX.format(company) + '/99999/' + action).status_code == 404
        assert replace(client, company, 99999).status_code == 404
        assert client.delete(PREFIX.format(company) + '/99999').status_code == 404
    for action in ('view', 'download'):
        assert client.get(PREFIX.format(2) + '/99999/' + action).status_code == 404
    assert replace(client, 2, 99999).status_code == 404
    assert client.delete(PREFIX.format(2) + '/99999').status_code == 404
    with Session() as db:
        assert db.query(ComplianceCompany).count() == 2
        assert db.query(ComplianceAudit).count() == 0


@pytest.mark.parametrize('action', ['upload', 'replace', 'delete', 'view', 'download'])
@pytest.mark.parametrize('failure', ['audit', 'commit'])
def test_fail_closed_atomic_audit(harness, monkeypatch, action, failure):
    client, Session, _ = harness
    item = upload(client).json()['document']
    from app.routers import corporate_documents as router
    from app.models.corporate_document import CorporateDocument
    def fail(*args, **kwargs):
        raise RuntimeError('Injected test failure')
    with monkeypatch.context() as patch:
        if failure == 'audit':
            patch.setattr(router, 'audit_event', fail)
        else:
            patch.setattr(Session.class_, 'commit', fail)
        if action == 'upload':
            response = upload(client)
        elif action == 'replace':
            response = replace(client, 2, item['id'])
        elif action == 'delete':
            response = client.delete(PREFIX.format(2) + f"/{item['id']}")
        else:
            response = client.get(item[action + '_url'])
        assert response.status_code == 500
        assert b'%PDF' not in response.content
    with Session() as db:
        assert db.query(CorporateDocument).count() == 1
        assert db.get(CorporateDocument, item['id']).status == 'active'
        assert db.query(ComplianceAudit).count() == 1
    assert client.get(item['view_url']).content == pdf()


def test_audit_excludes_freeform_notes(harness):
    client, Session, _ = harness
    item = upload(client, notes='sensitive user-entered note').json()['document']
    client.get(item['view_url'])
    with Session() as db:
        for audit in db.query(ComplianceAudit):
            data = json.loads(audit.new_value)
            assert 'notes' not in data
            assert 'content' not in data and 'storage_key' not in data
            assert data['id'] == item['id']


def test_replacement_validation_leaves_old_active(harness):
    client, Session, _ = harness
    item = upload(client).json()['document']
    assert replace(client, 2, item['id'], content=b'%PDF-fake').status_code == 400
    assert replace(client, 2, item['id'], notes='x' * 4001).status_code == 400
    assert client.get(PREFIX.format(2)).json()['documents'][0]['status'] == 'active'
    with Session() as db:
        assert db.query(ComplianceAudit).count() == 1


def test_replacement_history_soft_delete_and_audits(harness):
    client, Session, _ = harness
    old = upload(client, category='Bylaws').json()['document']
    response = replace(client, 2, old['id'])
    assert response.status_code == 201, response.text
    new = response.json()['document']
    assert new['id'] != old['id'] and new['replaced_document_id'] == old['id']
    assert new['document_type'] == 'Bylaws' and new['notes'] == 'New version'
    listing = client.get(PREFIX.format(2)).json()['documents']
    assert {d['id']: d['status'] for d in listing} == {old['id']: 'replaced', new['id']: 'active'}
    assert client.get(old['view_url']).content == pdf()
    assert client.get(old['download_url']).content == pdf()
    assert client.get(new['download_url']).content == pdf() + b'\n%new'
    assert replace(client, 2, old['id']).status_code == 409
    for item in (old, new):
        assert client.delete(PREFIX.format(2) + f"/{item['id']}").status_code == 204
        assert client.get(item['view_url']).status_code == 404
        assert client.get(item['download_url']).status_code == 404
        assert replace(client, 2, item['id']).status_code == 404
        assert client.delete(PREFIX.format(2) + f"/{item['id']}").status_code == 404
    assert client.get(PREFIX.format(2)).json()['documents'] == []
    from app.models.corporate_document import CorporateDocument
    with Session() as db:
        assert db.query(CorporateDocument).count() == 2
        assert db.get(CorporateDocument, old['id']).content == pdf()
        audits = db.query(ComplianceAudit).all()
        assert len(audits) == 7
        change = next(a for a in audits if a.field == 'corporate_document.replace')
        assert json.loads(change.old_value)['id'] == old['id']
        assert json.loads(change.new_value)['id'] == new['id']
        assert sum(a.field == 'corporate_document.delete' for a in audits) == 2


def test_view_download_audited_private_safe_headers(harness):
    client, Session, login = harness
    item = upload(client, filename='../naïve"report.pdf').json()['document']
    login('READ')
    for action, disposition in [('view', 'inline'), ('download', 'attachment')]:
        response = client.get(item[action + '_url'])
        assert response.status_code == 200, response.text
        assert response.content == pdf()
        assert response.headers['content-type'] == 'application/pdf'
        assert 'private' in response.headers['cache-control'] and 'no-store' in response.headers['cache-control']
        assert response.headers['x-content-type-options'] == 'nosniff'
        header = response.headers['content-disposition']
        assert header.startswith(disposition + ';') and "filename*=UTF-8''" in header
        assert '%C3%AF' in header
    with Session() as db:
        audits = db.query(ComplianceAudit).order_by(ComplianceAudit.id).all()
        assert [a.field for a in audits] == ['corporate_document.upload', 'corporate_document.view', 'corporate_document.download']
        assert all(a.user_id == 'READ' and json.loads(a.new_value)['id'] == item['id'] for a in audits[1:])


def test_pdf_validation_and_safe_filename(harness):
    client, Session, _ = harness
    for kwargs, expected in [
        ({'category': 'Tax return'}, 400),
        ({'content': b'<html>not pdf</html>'}, 400),
        ({'content': b'%PDF-1.7\nnot really a PDF'}, 400),
        ({'content': pdf(encrypted=True)}, 400),
        ({'filename': 'record.exe'}, 400),
        ({'mime': 'text/plain'}, 400),
        ({'content': b'%PDF-' + b'x' * (20 * 1024 * 1024)}, 413),
        ({'notes': 'x' * 4001}, 400),
    ]:
        response = upload(client, **kwargs)
        assert response.status_code == expected, (kwargs.keys(), response.status_code)
    with Session() as db:
        assert db.query(ComplianceAudit).count() == 0
    response = upload(client, filename='../secret/naïve"report.pdf', notes='x' * 4000)
    assert response.status_code == 201
    name = response.json()['document']['original_file_name']
    assert '/' not in name and '\\' not in name and '\r' not in name and '\n' not in name


def test_upload_list_multiple_categories_private_storage_audit(harness):
    client, Session, login = harness
    login('EDIT')
    ids = []
    for category in CATEGORIES + ['EIN']:
        response = upload(client, category=category)
        assert response.status_code == 201, response.text
        item = response.json()['document']
        assert item['company_id'] == 2 and item['document_type'] == category
        assert item['uploaded_by_user_id'] == 'EDIT' and item['uploaded_at']
        assert item['notes'] == 'Filed' and item['status'] == 'active'
        assert item['replaced_document_id'] is None
        assert not any('expiration' in key for key in item)
        assert not {'content', 'storage_key'} & item.keys()
        ids.append(item['id'])
    listing = client.get(PREFIX.format(2)).json()
    assert listing['categories'] == CATEGORIES
    assert listing['can_edit'] is True
    assert {d['id'] for d in listing['documents']} == set(ids)
    from app.models.corporate_document import CorporateDocument
    with Session() as db:
        rows = db.query(CorporateDocument).all()
        assert len({uuid.UUID(row.storage_key) for row in rows}) == 7
        assert all(row.content == pdf() for row in rows)
        assert [(c.id, c.ein) for c in db.query(ComplianceCompany).order_by(ComplianceCompany.id)] == [(2, 'preserve-A'), (3, 'preserve-B')]
        audits = db.query(ComplianceAudit).all()
        assert len(audits) == 7
        assert all(a.field == 'corporate_document.upload' and a.company_id == 2 and a.user_id == 'EDIT' and a.created_at for a in audits)
        assert {json.loads(a.new_value)['id'] for a in audits} == set(ids)
        assert all('%PDF' not in a.new_value for a in audits)
