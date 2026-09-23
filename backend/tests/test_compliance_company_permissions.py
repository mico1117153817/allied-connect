from tests.test_compliance import harness
from app.models.database import get_db
from app.models.compliance_company import CompanyPermission
from app.models.compliance_migration import migrate_compliance
from sqlalchemy import create_engine


def test_allied_requires_explicit_grant_and_revocation_sticks(harness):
    client, current = harness
    client.get('/api/compliance')
    current['user'] = {'timestation_id': 'LATER_ADMIN', 'name': 'Restricted', 'role': 'admin'}
    assert client.get('/api/compliance').status_code == 403
    assert client.get('/api/compliance/companies').json()['companies'] == []
    with next(client.app.dependency_overrides[get_db]()) as db:
        db.add(CompanyPermission(employee_id='LATER_ADMIN', company_id=1, can_edit=True))
        db.commit()
    assert client.get('/api/compliance').status_code == 200
    with next(client.app.dependency_overrides[get_db]()) as db:
        db.query(CompanyPermission).filter_by(employee_id='LATER_ADMIN').delete()
        db.commit()
    assert client.get('/api/compliance').status_code == 403
    assert client.get('/api/compliance/Alabama/portal-credentials').status_code == 403
    assert client.put('/api/compliance/Alabama', json={}).status_code == 403


def test_migration_preserves_existing_admin_access_as_revocable_grants(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as c:
        c.exec_driver_sql('CREATE TABLE state_compliance (id INTEGER PRIMARY KEY, state TEXT UNIQUE NOT NULL)')
        c.exec_driver_sql("INSERT INTO state_compliance VALUES (1, 'Colorado')")
        c.exec_driver_sql('CREATE TABLE compliance_attachments (id INTEGER PRIMARY KEY, state TEXT)')
        c.exec_driver_sql('CREATE TABLE employees (timestation_id TEXT, role TEXT)')
        c.exec_driver_sql("INSERT INTO employees VALUES ('EXISTING_ADMIN','admin'), ('EMPLOYEE','employee')")
    backup = tmp_path / 'backup.db'
    migrate_compliance(engine, backup)
    with engine.begin() as c:
        assert c.exec_driver_sql('SELECT employee_id, company_id, can_edit FROM compliance_company_permissions').fetchall() == [('EXISTING_ADMIN', 1, True)]
        c.exec_driver_sql('DELETE FROM compliance_company_permissions')
    migrate_compliance(engine, backup)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT COUNT(*) FROM compliance_company_permissions').scalar() == 0
