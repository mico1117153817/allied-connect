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
