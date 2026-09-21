import pytest
from tests.test_compliance import harness
from app.models.database import get_db
from app.models.compliance_company import ComplianceCompany
from app.routers import compliance


def test_archive_partial_update_preserves_company_profile(harness):
    client, _ = harness
    company = client.post('/api/compliance/companies', json={'legal_name': 'Archive B', 'ein': 'fixture-only'}).json()
    response = client.put(f"/api/compliance/companies/{company['id']}", json={'is_active': False})
    assert response.status_code == 200
    assert response.json()['legal_name'] == 'Archive B'
    assert response.json()['ein'] == 'fixture-only'
    assert response.json()['is_active'] is False


@pytest.mark.parametrize('name', [None, '', '   '])
def test_company_name_cannot_be_cleared(harness, name):
    client, _ = harness
    company = client.post('/api/compliance/companies', json={'legal_name': 'Keep Name'}).json()
    assert client.put(f"/api/compliance/companies/{company['id']}", json={'legal_name': name}).status_code == 422


def test_new_company_has_no_issued_statuses(harness):
    client, _ = harness
    for source in (None, 1):
        company = client.post('/api/compliance/companies', json={'legal_name': 'New', 'copy_from_company_id': source}).json()
        rows = client.get('/api/compliance', params={'company_id': company['id']}).json()['states']
        assert len(rows) == 51
        assert all(row[key] == 'Not Held' for row in rows for key in ('license_status', 'coa_status', 'bond_status'))


def test_failed_requirement_copy_leaves_no_partial_company(harness, monkeypatch):
    client, _ = harness
    client.get('/api/compliance')
    monkeypatch.setattr(compliance, 'REQUIREMENT_COPY_FIELDS', ('nonexistent_copy_field',))
    with pytest.raises(AttributeError):
        client.post('/api/compliance/companies', json={'legal_name': 'Must Roll Back', 'copy_from_company_id': 1})
    with next(client.app.dependency_overrides[get_db]()) as db:
        assert db.query(ComplianceCompany).filter_by(legal_name='Must Roll Back').count() == 0


def test_archived_pdf_history_is_discoverable_and_scoped(harness):
    client, _ = harness
    b = client.post('/api/compliance/companies', json={'legal_name': 'Document B'}).json()['id']
    params = {'company_id': b}
    pdf = b'%PDF-1.4 history fixture'
    attachment = client.post('/api/compliance/Colorado/attachments', params=params, data={'item_type': 'license'}, files={'file': ('history.pdf', pdf, 'application/pdf')}).json()['attachment']
    assert client.delete(f"/api/compliance/Colorado/attachments/{attachment['id']}", params=params).status_code == 204
    assert client.get('/api/compliance/Colorado/attachments', params=params).json()['attachments'] == []
    history = client.get('/api/compliance/Colorado/attachments', params={**params, 'include_archived': True}).json()['attachments']
    assert len(history) == 1 and history[0]['archived_at'] and history[0]['is_archived']
    assert client.get(history[0]['view_url']).content == pdf
    assert client.get('/api/compliance/Colorado/attachments', params={'company_id': 1, 'include_archived': True}).json()['attachments'] == []
