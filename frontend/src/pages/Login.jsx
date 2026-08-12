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
    <main className="login-shell">
      <div className="login-bridge-art" aria-hidden="true">
        <div className="bridge-deck" />
        <div className="bridge-tower bridge-tower-left" />
        <div className="bridge-tower bridge-tower-right" />
        <div className="bridge-cable bridge-cable-left" />
        <div className="bridge-cable bridge-cable-right" />
      </div>
      <div className="login-sweep login-sweep-one" aria-hidden="true" />
      <div className="login-sweep login-sweep-two" aria-hidden="true" />

      <section className="login-content">
        <header className="login-heading">
          <h1>ALLIED CONNECT</h1>
          <p>EMPLOYEE PORTAL</p>
        </header>

        <section className="login-card" aria-label="Employee portal sign in">
          <img src="/allied-logo.jpg" alt="Allied Alliance Group Inc." className="login-logo" />
          <p className="login-prompt">Sign in with your PIN</p>
          <form onSubmit={handleSubmit} className="login-form">
            <label htmlFor="pin" className="sr-only">Enter PIN</label>
            <input
              id="pin"
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              placeholder="Enter PIN"
              maxLength="4"
              className="login-pin"
              autoFocus
            />
            {error && <p className="login-error" role="alert">{error}</p>}
            <button type="submit" disabled={loading || pin.length < 4} className="login-button">
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </section>
      </section>
    </main>
  )
}
