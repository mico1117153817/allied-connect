import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { isLoggedIn, isManager } from './lib/auth'
import { api } from './lib/api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import TimeOff from './pages/TimeOff'
import Manager from './pages/Manager'
import Documents from './pages/Documents'
import ManageDocuments from './pages/ManageDocuments'
import Settings from './pages/Settings'
import MyInfo from './pages/MyInfo'
import EmployeeDirectory from './pages/EmployeeDirectory'

function ProtectedRoute({ children, managerOnly = false }) {
  const location = useLocation()
  const loggedIn = isLoggedIn()
  const { data: profileStatus, isLoading: profileLoading } = useQuery({
    queryKey: ['profile-status'],
    queryFn: () => api.get('/api/me/profile-status').then(r => r.data),
    enabled: loggedIn,
    staleTime: 15000,
  })
  const { data: documentStatus, isLoading: documentsLoading } = useQuery({
    queryKey: ['document-requirements'],
    queryFn: () => api.get('/api/documents/requirements').then(r => r.data),
    enabled: loggedIn && !!profileStatus?.is_complete,
    staleTime: 15000,
  })
  if (!loggedIn) return <Navigate to="/login" state={{ from: location }} replace />
  if (profileLoading) return <div className="min-h-screen flex items-center justify-center text-gray-500">Checking your profile...</div>
  if (!profileStatus?.is_complete && location.pathname !== '/my-info') return <Navigate to="/my-info" replace />
  if (managerOnly && !isManager()) return <Navigate to="/dashboard" replace />
  if (documentsLoading && profileStatus?.is_complete) return <div className="min-h-screen flex items-center justify-center text-gray-500">Checking documents...</div>
  if (documentStatus?.has_blocking_documents && location.pathname !== '/documents') return <Navigate to="/documents" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={isLoggedIn() ? <Navigate to={isManager() ? '/manager' : '/dashboard'} replace /> : <Login />} />
      <Route path="/my-info" element={<ProtectedRoute><MyInfo /></ProtectedRoute>} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/time-off" element={<ProtectedRoute><TimeOff /></ProtectedRoute>} />
      <Route path="/manager" element={<ProtectedRoute managerOnly><Manager /></ProtectedRoute>} />
      <Route path="/documents" element={<ProtectedRoute><Documents /></ProtectedRoute>} />
      <Route path="/manage-documents" element={<ProtectedRoute managerOnly><ManageDocuments /></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute managerOnly><Settings /></ProtectedRoute>} />
      <Route path="/directory" element={<ProtectedRoute><EmployeeDirectory /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
