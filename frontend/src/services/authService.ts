import api, { setTokens, clearTokens } from './api'
import type { RegisterRequest, LoginRequest, AuthResponse } from '../types/api'
import type { User } from '../types/models'

export async function register(data: RegisterRequest): Promise<AuthResponse> {
  const response = await api.post<AuthResponse>('/auth/register', data)
  setTokens(response.data.access_token, response.data.refresh_token)
  return response.data
}

export async function login(data: LoginRequest): Promise<AuthResponse> {
  const response = await api.post<AuthResponse>('/auth/login', data)
  setTokens(response.data.access_token, response.data.refresh_token)
  return response.data
}

export async function logout(): Promise<void> {
  clearTokens()
}

export async function getMe(): Promise<User> {
  const response = await api.get<User>('/auth/me')
  return response.data
}
