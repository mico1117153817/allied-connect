"""Tenant boundary regression tests, using disposable in-memory databases only."""
from tests.test_compliance import harness
from app.models.database import get_db


def test_every_state_action_is_company_scoped(harness):
    client, _ = harness
    b = client.post('/api/compliance/companies', json={'legal_name': 'B'}).json()['id']
    q = {'company_id': b}
    payload = {'collection_license_requirement': 'Required', 'license_status': 'Active',
               'license_number': 'B-ONLY', 'portal_password': 'B-secret'}
    assert client.put('/api/compliance/Colorado', params=q, json=payload).json()['license_number'] == 'B-ONLY'
    allied = {r['state']: r for r in client.get('/api/compliance').json()['states']}
    assert allied['Colorado']['license_number'] != 'B-ONLY'
    assert client.get('/api/compliance/Colorado/portal-credentials', params=q).json()['password'] == 'B-secret'
    assert client.get('/api/compliance/Colorado/portal-credentials').json()['password'] is None
    assert client.post('/api/compliance/Colorado/annual-report/complete', params=q).status_code == 200
    assert {r['state']: r for r in client.get('/api/compliance').json()['states']}['Colorado']['annual_report_completed_at'] is None
    upload = client.post('/api/compliance/Colorado/attachments', params=q, data={'item_type': 'license'}, files={'file': ('b.pdf', b'%PDF B', 'application/pdf')})
    attachment = upload.json()['attachment']
    assert f'company_id={b}' in attachment['view_url']
    url = f"/api/compliance/Colorado/attachments/{attachment['id']}/view"
    assert client.get(url).status_code == 404
    assert client.get(url, params=q).content == b'%PDF B'
    assert client.get('/api/compliance/Colorado/attachments').json()['attachments'] == []
    assert client.delete(url.removesuffix('/view')).status_code == 404



def test_copy_only_requirements_never_evidence_or_credentials(harness):
    client, _ = harness
    client.put('/api/compliance/Colorado', json={
        'collection_license_requirement': 'Required', 'license_status': 'Active', 'license_number': 'SECRET',
        'bond_requirement': 'Required', 'bond_status': 'Active', 'bond_amount': 50000,
        'bond_requirement_amount': 25000, 'renewal_structure': 'Annual', 'general_requirement_notes': 'Rule only',
        'portal_username': 'private', 'portal_password': 'secret', 'notes': 'private notes',
        'source_urls': ['https://public.gov/rule'], 'regulator': 'State office', 'state_portal_url': 'https://state.gov'})
    b = client.post('/api/compliance/companies', json={'legal_name': 'Copy', 'copy_from_company_id': 1}).json()['id']
    row = {r['state']: r for r in client.get('/api/compliance', params={'company_id': b}).json()['states']}['Colorado']
    assert row['collection_license_requirement'] == 'Required'
    assert row['bond_requirement_amount'] == 25000
    assert row['renewal_structure'] == 'Annual' and row['general_requirement_notes'] == 'Rule only'
    assert row['regulator'] == 'State office'
    assert row['license_number'] is None and row['bond_amount'] is None
    assert row['portal_username'] is None and not row['has_portal_password']
    assert row['notes'] is None and row['source_urls'] == [] and row['document_paths'] == []
    assert row['license_status'] == 'Not Held'


def test_admin_access_is_explicit_and_archive_is_readonly(harness):
    client, current = harness
    b = client.post('/api/compliance/companies', json={'legal_name': 'Private'}).json()['id']
    current['user'] = {'timestation_id': 'RESTRICTED', 'name': 'Admin', 'role': 'admin'}
    assert client.get('/api/compliance', params={'company_id': b}).status_code == 403
    assert client.get('/api/compliance').status_code == 403
    assert client.get('/api/compliance/companies').json()['companies'] == []
    assert client.post('/api/compliance/companies', json={'legal_name': 'Steal', 'copy_from_company_id': b}).status_code == 403
    own = client.post('/api/compliance/companies', json={'legal_name': 'Mine'}).json()['id']
    assert client.get('/api/compliance', params={'company_id': own}).status_code == 200
    response = client.put(f'/api/compliance/companies/{own}', json={'legal_name': 'Mine', 'is_active': False})
    assert response.status_code == 200
    assert client.get('/api/compliance', params={'company_id': own}).json()['can_edit'] is False
    assert client.put('/api/compliance/Colorado', params={'company_id': own}, json={}).status_code == 403
    assert client.post('/api/compliance/Colorado/annual-report/complete', params={'company_id': own}).status_code == 403
    from app.models.compliance_company import CompanyPermission
    with next(client.app.dependency_overrides[get_db]()) as db:
        db.add(CompanyPermission(employee_id='RESTRICTED', company_id=b, can_edit=False))
        db.commit()
    assert client.get('/api/compliance', params={'company_id': b}).status_code == 200
    assert client.get('/api/compliance', params={'company_id': b}).json()['can_edit'] is False
    assert client.put('/api/compliance/Colorado', params={'company_id': b}, json={}).status_code == 403
    assert client.put(f'/api/compliance/companies/{b}', json={'legal_name': 'Stolen'}).status_code == 403


def test_audit_diffs_redact_secrets_and_pdf_archive_retains_bytes(harness):
    client, _ = harness
    b = client.post('/api/compliance/companies', json={'legal_name': 'Audited'}).json()['id']
    q = {'company_id': b}
    payload = {'notes': 'first', 'portal_username': 'private-user', 'portal_password': 'never-log-me'}
    assert client.put('/api/compliance/Colorado', params=q, json=payload).status_code == 200
    events = client.get(f'/api/compliance/companies/{b}/audit', params={'state': 'Colorado'})
    assert events.status_code == 200
    assert 'never-log-me' not in events.text and 'private-user' not in events.text
    note = next(e for e in events.json()['events'] if e['field'] == 'notes')
    assert note['old_value'] is None and note['new_value'] == 'first' and note['user_name'] == 'Marc'
    count = len(events.json()['events'])
    client.put('/api/compliance/Colorado', params=q, json={'notes': 'first', 'portal_username': 'private-user'})
    assert len(client.get(f'/api/compliance/companies/{b}/audit', params={'state': 'Colorado'}).json()['events']) == count
    upload = client.post('/api/compliance/Colorado/attachments', params=q, data={'item_type': 'license'}, files={'file': ('history.pdf', b'%PDF history', 'application/pdf')}).json()['attachment']
    url = f"/api/compliance/Colorado/attachments/{upload['id']}"
    assert client.delete(url, params=q).status_code == 204
    assert client.get(url+'/view', params={**q, 'include_archived': True}).content == b'%PDF history'
    assert client.get('/api/compliance/Colorado/attachments', params=q).json()['attachments'] == []
    from app.models.compliance_attachment import ComplianceAttachment
    with next(client.app.dependency_overrides[get_db]()) as db:
        assert db.get(ComplianceAttachment, upload['id']).archived_at is not None
    client.post('/api/compliance/Colorado/annual-report/complete', params=q)
    client.put(f'/api/compliance/companies/{b}', json={'legal_name': 'Renamed', 'is_active': False})
    fields = {e['field'] for e in client.get(f'/api/compliance/companies/{b}/audit').json()['events']}
    assert {'annual_report_completed_at', 'legal_name', 'is_active', 'attachment.upload', 'attachment.archive'} <= fields


def test_company_summaries_use_inclusive_forward_windows(harness):
    from datetime import date, timedelta
    from app.models.state_compliance import StateCompliance
    client, _ = harness
    b = client.post('/api/compliance/companies', json={'legal_name': 'Summary'}).json()['id']
    with next(client.app.dependency_overrides[get_db]()) as db:
        rows = db.query(StateCompliance).filter_by(company_id=b).order_by(StateCompliance.id).all()
        for row, days in zip(rows, [-1, 0, 30, 31, 60, 61, 90, 91]):
            row.collection_license_requirement = 'Required'
            row.license_status = 'Active'
            row.license_expiration = date.today() + timedelta(days=days)
        rows[2].bond_requirement = 'Required'
        rows[2].bond_expiration = date.today() + timedelta(days=90)
        rows[2].annual_report_requirement = 'Annual'
        rows[2].annual_report_due_date = date.today()
        db.commit()
    response = client.get(f'/api/compliance/companies/{b}')
    assert response.status_code == 200
    summary = response.json()['summary']
    assert summary['total'] == 51
    assert [summary[f'licenses_expiring_{d}'] for d in (30, 60, 90)] == [2, 4, 6]
    assert summary['bonds_expiring_soon'] == 1 and summary['annual_reports_due_soon'] == 1
    assert summary['expiring_soon'] == 6
    states = client.get('/api/compliance', params={'company_id': b}).json()['states']
    assert summary['open_issues'] == sum(bool(r['issues']) for r in states)
    assert all(k in summary for k in ('active', 'needs_review', 'not_authorized'))


def test_logo_validated_durable_and_company_protected(harness):
    import base64
    client, current = harness
    b = client.post('/api/compliance/companies', json={'legal_name': 'Logo'}).json()['id']
    url = f'/api/compliance/companies/{b}/logo'
    assert client.post(url, files={'file': ('bad.svg', b'<svg/>', 'image/svg+xml')}).status_code == 400
    assert client.post(url, files={'file': ('bad.png', b'\x89PNG\r\n\x1a\nnot an image', 'image/png')}).status_code == 400
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')
    response = client.post(url, files={'file': ('logo.png', png, 'image/png')})
    assert response.status_code == 200, response.text
    assert response.json()['logo_path'].startswith(url + '?v=')
    assert client.get(response.json()['logo_path']).content == png
    assert client.get(url).headers['content-type'] == 'image/png'
    assert client.get(url).content == png
    current['user'] = {'timestation_id': 'OTHER', 'role': 'admin', 'name': 'Other'}
    assert client.get(url).status_code == 403


def test_company_creation_has_blank_independent_register(harness):
    client, _ = harness
    legacy = client.get('/api/compliance').json()
    response = client.post('/api/compliance/companies', json={'legal_name': 'Second Company'})
    assert response.status_code == 201, response.text
    company = response.json()
    assert company['id'] != legacy['company']['id']
    result = client.get('/api/compliance', params={'company_id': company['id']}).json()
    assert result['company']['legal_name'] == 'Second Company'
    assert len(result['states']) == 51
    assert all(r['license_number'] is None and r['document_paths'] == [] for r in result['states'])
    assert result['can_edit'] is True
    listing = client.get('/api/compliance/companies').json()
    assert len(listing['companies']) == 2
    assert listing['is_super_admin'] and listing['can_manage']
