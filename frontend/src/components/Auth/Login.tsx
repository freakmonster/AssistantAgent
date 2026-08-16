// 登录表单
import { useState } from 'react'
import { authApi } from '../../services/api'
import { useUserStore } from '../../stores/userStore'

interface LoginProps {
  onSwitch: () => void
}

export function Login({ onSwitch }: LoginProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const setAuth = useUserStore((s) => s.setAuth)

  const handleSubmit = async () => {
    setError('')
    try {
      const resp = await authApi.login(email.trim(), password)
      setAuth(resp.access_token, { id: '', email: email.trim() })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-form">
        <h2>登录</h2>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="邮箱"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="密码"
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleSubmit()
          }}
        />
        {error && <div className="auth-error">{error}</div>}
        <button onClick={() => void handleSubmit()}>登录</button>
        <button className="link-btn" onClick={onSwitch}>
          没有账号？注册
        </button>
      </div>
    </div>
  )
}
