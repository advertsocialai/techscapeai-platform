export interface LoginPayload {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in_min: number
}

export interface RegisterPayload {
  user_first_name: string
  user_last_name: string
  contact_email: string
  contact_phone: string
  user_password: string
  business_name: string
  industry: string
  timezone: string
  website_url?: string
  terms_accepted_at: string
  terms_version: string
  marketing_opt_in: boolean
}

export interface PersonalInfoData {
  firstName: string
  lastName: string
  email: string
  phone: string
  countryCode: string
  password: string
}

export interface AddressData {
  streetAddress: string
  city: string
  state: string
  postalCode: string
  country: string
  company: string
}

export interface TermsData {
  termsAccepted: boolean
  ageConfirmed: boolean
  marketingOptIn: boolean
}

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  role: string
}