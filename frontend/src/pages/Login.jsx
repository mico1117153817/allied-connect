import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function Login() {
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const resp = await api.post('/auth/login', { pin })
      localStorage.setItem('token', resp.data.access_token)
      localStorage.setItem('employee', JSON.stringify(resp.data.employee))
      const managementRoles = ['manager', 'super_admin']
      navigate(managementRoles.includes(resp.data.employee.role) ? '/manager' : '/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-900 to-indigo-900">
      <div className="max-w-2xl w-full space-y-8 p-8 bg-white rounded-2xl shadow-xl">
        <div className="text-center">
          <img src="/allied-logo.jpg" alt="Allied Alliance Group Inc." className="mx-auto mb-2 w-full h-auto max-w-lg rounded-lg" />
          <p className="mt-2 text-sm text-gray-600">
            Sign in with your PIN
          </p>
        </div>
        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          <div>
            <input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              placeholder="Enter PIN"
              maxLength="4"
              className="w-full px-4 py-4 border-2 border-gray-300 rounded-xl text-center text-3xl tracking-[0.5em] focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none transition"
              autoFocus
            />
          </div>
          {error && (
            <p className="text-red-500 text-sm text-center bg-red-50 py-2 px-4 rounded-lg">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading || pin.length < 4}
            className="w-full py-3 bg-blue-700 text-white rounded-xl hover:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed font-semibold text-lg transition"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
