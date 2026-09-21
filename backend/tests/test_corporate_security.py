"""Security regressions; use the real isolated HTTP/JWT harness."""
import pytest
from tests.test_corporate_documents import harness, upload, replace
from app.models.compliance_company import ComplianceCompany, CompanyPermission
from app.models.employee import Employee
from app.models.corporate_document import CorporateDocument
from app.models.compliance_audit import ComplianceAudit
from app.routers import corporate_documents as router


def compressed_pdf(sizes):
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter()
    for size in sizes:
        page = writer.add_blank_page(width=72, height=72)
        stream = DecodedStreamObject()
        stream.set_data(b' ' * size)
        page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.parametrize('sizes', [[9 * 1024 * 1024], [7 * 1024 * 1024] * 5, [0] * 251])
def test_pdf_decoded_and_page_budgets(harness, sizes):
    client, Session, _ = harness
    content = compressed_pdf(sizes)
    assert len(content) < 100_000  # safe reproduction, never destructive stress
    response = upload(client, content=content)
    assert response.status_code == 400, response.text
    with Session() as db:
        assert db.query(CorporateDocument).count() == 0
        assert db.query(ComplianceAudit).count() == 0



@pytest.mark.parametrize('length', [None, '1', '999999999'])
@pytest.mark.parametrize('suffix', ['', '/1/replace'])
def test_body_limit_before_parser(harness, monkeypatch, length, suffix):
    import asyncio
    from starlette.formparsers import MultiPartParser
    client, _, _ = harness
    monkeypatch.setattr(router, 'MAX_BODY_BYTES', 32, raising=False)
    entered = []
    async def forbidden_parse(*args, **kwargs):
        entered.append(True)
        raise AssertionError('Multipart parser must not receive oversized bodies')
    monkeypatch.setattr(MultiPartParser, 'parse', forbidden_parse)
    messages = iter([{'type': 'http.request', 'body': b'x' * 20, 'more_body': True},
                     {'type': 'http.request', 'body': b'y' * 20, 'more_body': False}])
    sent = []
    async def receive():
        return next(messages)
    async def send(message):
        sent.append(message)
    headers = [(b'content-type', b'multipart/form-data; boundary=x')]
    if length is not None:
        headers.append((b'content-length', length.encode()))
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/compliance/companies/2/corporate-documents' + suffix,
             'headers': headers, 'query_string': b'', 'root_path': '', 'scheme': 'http',
             'server': ('test', 80), 'client': ('test', 1), 'http_version': '1.1'}
    asyncio.run(client.app(scope, receive, send))
    assert sent[0]['status'] == 413, sent
    assert not entered



@pytest.mark.parametrize('action', ['upload', 'replace'])
@pytest.mark.parametrize('change', ['revoked', 'archived', 'disabled', 'demoted'])
def test_validation_interleave_reauthorizes(harness, monkeypatch, action, change):
    client, Session, login = harness
    item = upload(client).json()['document']
    login('EDIT')
    original = router.validated_pdf
    async def interleave(*args):
        result = await original(*args)
        with Session() as db:
            if change == 'revoked':
                db.query(CompanyPermission).filter_by(employee_id='EDIT').delete()
            elif change == 'archived':
                db.get(ComplianceCompany, 2).is_active = False
            elif change == 'disabled':
                db.query(Employee).filter_by(timestation_id='EDIT').one().login_enabled = False
            else:
                db.query(Employee).filter_by(timestation_id='EDIT').one().role = 'employee'
            db.commit()
        return result
    monkeypatch.setattr(router, 'validated_pdf', interleave)
    response = upload(client) if action == 'upload' else replace(client, 2, item['id'])
    assert response.status_code == 403, response.text
    with Session() as db:
        assert db.query(CorporateDocument).count() == 1
        assert db.get(CorporateDocument, item['id']).status == 'active'
        assert db.query(ComplianceAudit).count() == 1
