from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from io import BytesIO
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.test_compliance import harness
from app.models.database import get_db
from app.models.setting import Setting
from app.models.state_compliance import StateCompliance
from app.models.compliance_audit import ComplianceAudit
from app.routers import compliance


def test_first_password_key_and_edit_roll_back_with_failed_audit(harness, monkeypatch):
    client, _ = harness
    monkeypatch.setattr(compliance.settings, 'COMPLIANCE_CREDENTIAL_KEY', '')
    company = client.post('/api/compliance/companies', json={'legal_name': 'Atomic Credentials'}).json()['id']
    params = {'company_id': company}
    with monkeypatch.context() as patcher:
        def fail(*args):
            raise RuntimeError('forced late audit failure')
        patcher.setattr(compliance, 'audit_diff', fail)
        with pytest.raises(RuntimeError, match='forced late'):
            client.put('/api/compliance/Colorado', params=params, json={'notes': 'must roll back', 'portal_password': 'synthetic-only'})
    with next(client.app.dependency_overrides[get_db]()) as db:
        row = db.query(StateCompliance).filter_by(company_id=company, state='Colorado').one()
        assert row.notes is None and row.portal_password_encrypted is None
        assert db.query(Setting).filter_by(key='compliance_credential_key').count() == 0
        assert db.query(ComplianceAudit).filter_by(company_id=company, state='Colorado').count() == 0
    assert client.put('/api/compliance/Colorado', params=params, json={'notes': 'saved', 'portal_password': 'synthetic-only'}).status_code == 200
    assert client.get('/api/compliance/Colorado/portal-credentials', params=params).json()['password'] == 'synthetic-only'


def test_concurrent_first_key_creation_uses_one_transactional_key(tmp_path, monkeypatch):
    monkeypatch.setattr(compliance.settings, 'COMPLIANCE_CREDENTIAL_KEY', '')
    engine = create_engine(f"sqlite:///{tmp_path / 'keys.db'}")
    Setting.__table__.create(engine)
    barrier = Barrier(2)
    def worker():
        with Session(engine) as db:
            barrier.wait(timeout=5)
            key = compliance._credential_key(db)
            db.commit()
            return key
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        values = [future.result(timeout=10) for future in futures]
    assert values[0] == values[1]
    with Session(engine) as db:
        assert db.query(Setting).count() == 1
    engine.dispose()


def test_logo_replacement_changes_fetch_revision(harness):
    client, _ = harness
    company = client.post('/api/compliance/companies', json={'legal_name': 'Logo Revision'}).json()['id']
    def png(color):
        output = BytesIO()
        Image.new('RGB', (1, 1), color).save(output, format='PNG')
        return output.getvalue()
    first = client.post(f'/api/compliance/companies/{company}/logo', files={'file': ('logo.png', png('red'), 'image/png')}).json()
    second_bytes = png('blue')
    second = client.post(f'/api/compliance/companies/{company}/logo', files={'file': ('logo.png', second_bytes, 'image/png')}).json()
    assert first['logo_path'] != second['logo_path']
    assert client.get(second['logo_path']).content == second_bytes
