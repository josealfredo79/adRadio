import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import axios from 'axios'
import api, { setAccessToken } from '@/lib/api'

interface User {
  id: string
  email: string
  role: string
  business_name: string | null
  business_category: string | null
  city: string | null
  country: string
  phone: string | null
  whatsapp_number: string | null
  language: string
  bot_name: string | null
  bot_personality: string | null
  subscription_status: string
  current_plan: string
  messages_remaining: number
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (email: string, password: string, businessName?: string) => Promise<void>
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Restore session using httpOnly cookie — no localStorage needed
    axios
      .post('/api/v1/auth/refresh', null, { withCredentials: true })
      .then(({ data }) => {
        setAccessToken(data.access_token)
        return api.get('/me')
      })
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const { data } = await api.post('/auth/login', { email, password })
    setAccessToken(data.access_token)
    // refresh_token is now set as httpOnly cookie by the backend
    const me = await api.get('/me')
    setUser(me.data)
  }

  const logout = async () => {
    await api.post('/auth/logout').catch(() => {})
    setAccessToken(null)
    setUser(null)
  }

  const register = async (email: string, password: string, businessName?: string) => {
    await api.post('/auth/register', {
      email,
      password,
      business_name: businessName,
    })
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, register, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
