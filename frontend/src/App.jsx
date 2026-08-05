import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { isLoggedIn, isManager } from './lib/auth'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import TimeOff from './pages/TimeOff'
import Manager from './pages/Manager'
import Documents from './pages/Documents'
import ManageDocuments from './pages/ManageDocuments'
import Settings from './pages/Settings'

function ProtectedRoute({ children, managerOnly = false }) {
  const location = useLocation()
  if (!isLoggedIn()) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  if (managerOnly && !isManager()) {
    return <Navigate to="/dashboard" replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={
        isLoggedIn() ? <Navigate to={isManager() ? '/manager' : '/dashboard'} replace /> : <Login />
      } />
      <Route path="/dashboard" element={
        <ProtectedRoute><Dashboard /></ProtectedRoute>
      } />
      <Route path="/time-off" element={
        <ProtectedRoute><TimeOff /></ProtectedRoute>
      } />
      <Route path="/manager" element={
        <ProtectedRoute managerOnly><Manager /></ProtectedRoute>
      } />
      <Route path="/documents" element={
        <ProtectedRoute><Documents /></ProtectedRoute>
      } />
      <Route path="/manage-documents" element={
        <ProtectedRoute managerOnly><ManageDocuments /></ProtectedRoute>
      } />
      <Route path="/settings" element={
        <ProtectedRoute managerOnly><Settings /></ProtectedRoute>
      } />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
