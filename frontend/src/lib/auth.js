export function getEmployee() {
  const raw = localStorage.getItem('employee')
  return raw ? JSON.parse(raw) : null
}

export function getToken() {
  return localStorage.getItem('token')
}

export function isLoggedIn() {
  return !!getToken()
}

export function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('employee')
  window.location.href = '/login'
}

export function isManager() {
  const emp = getEmployee()
  return emp?.role === 'manager' || emp?.role === 'super_admin'
}

export function canAccessCompliance() {
  const emp = getEmployee()
  return emp?.role === 'admin' || emp?.role === 'super_admin'
}

export function isSuperAdmin() {
  const emp = getEmployee()
  return emp?.role === 'super_admin'
}

export function canAccessPasswordVault() {
  return getEmployee()?.password_vault_access === true
}

export function canAccessCompanyTasks() {
  return getEmployee()?.company_task_access === true
}

export function canAccessCompanyCalendar() {
  return getEmployee()?.company_calendar_access === true
}

export function canAdministerPasswordVault() {
  return ['local_f2a5804ba2e5', 'local_262a0ca4abea'].includes(getEmployee()?.timestation_id)
}
