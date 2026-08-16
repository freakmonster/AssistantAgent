// 注册表单
import { useState } from 'react'
import { authApi } from '../../services/api'
import { useTranslation } from '../../stores/settingsStore'
import { useUserStore } from '../../stores/userStore'

interface RegisterProps {
  onSwitch: () => void
}

export function Register({ onSwitch }: RegisterProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const { t } = useTranslation()
  const setAuth = useUserStore((s) => s.setAuth)

  const handleSubmit = async () => {
    setError('')
    try {
      const resp = await authApi.register(email.trim(), password)
      setAuth(resp.access_token, { id: '', email: email.trim() })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-form">
        <h2>{t.auth.register}</h2>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t.auth.email}
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t.auth.password}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleSubmit()
          }}
        />
        {error && <div className="auth-error">{error}</div>}
        <button onClick={() => void handleSubmit()}>{t.auth.register}</button>
        <button className="link-btn" onClick={onSwitch}>
          {t.auth.toLogin}
        </button>
      </div>
    </div>
  )
}
