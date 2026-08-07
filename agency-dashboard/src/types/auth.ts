export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  business_name: string
  contact_email: string
  contact_phone?: string
  industry?: string
  user_first_name?: string
  user_last_name?: string
  user_password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in_min: number
}

export interface BusinessUser {
  id: string
  business_id: string
  email: string
  first_name: string | null
  last_name: string | null
  role: 'admin' | 'manager' | 'user' | 'viewer'
  status: string
}

export interface ForgotPasswordPayload {
  email: string
}

export interface ResetPasswordPayload {
  token: string
  new_password: string
}

export interface MeResponse {
  id: string
  name: string
  contact_email: string
  status: string
  subscription_tier: string
  user: BusinessUser
}
