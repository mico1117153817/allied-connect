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

function ProtectedRoute({ children, managerOnly = false }) {
  const location = useLocation()
  const loggedIn = isLoggedIn()
  const { data, isLoading } = useQuery({
    queryKey: ['document-requirements'],
    queryFn: () => api.get('/api/documents/requirements').then(r => r.data),
    enabled: loggedIn,
    staleTime: 15000,
  })
  if (!loggedIn) return <Navigate to="/login" state={{ from: location }} replace />
  if (managerOnly && !isManager()) return <Navigate to="/dashboard" replace />
  if (isLoading) return <div className="min-h-screen flex items-center justify-center text-gray-500">Checking documents...</div>
  if (data?.has_blocking_documents && location.pathname !== '/documents') return <Navigate to="/documents" replace />
  return (
    <>
      {data?.has_new_documents && location.pathname !== '/documents' && !data?.has_blocking_documents && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white max-w-md w-full rounded-2xl shadow-2xl p-6">
            <h2 className="text-xl font-bold text-gray-900">New Document Received</h2>
            <p className="text-gray-600 mt-2">You have {data.new_documents.length} new document(s) from management.</p>
            <a href="/documents" className="inline-block mt-5 px-5 py-2 bg-blue-600 text-white rounded-lg">Review Documents</a>
          </div>
        </div>
      )}
      {children}
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={isLoggedIn() ? <Navigate to={isManager() ? '/manager' : '/dashboard'} replace /> : <Login />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/time-off" element={<ProtectedRoute><TimeOff /></ProtectedRoute>} />
      <Route path="/manager" element={<ProtectedRoute managerOnly><Manager /></ProtectedRoute>} />
      <Route path="/documents" element={<ProtectedRoute><Documents /></ProtectedRoute>} />
      <Route path="/manage-documents" element={<ProtectedRoute managerOnly><ManageDocuments /></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute managerOnly><Settings /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
