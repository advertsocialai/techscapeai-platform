import axios from "axios"

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api/techscape/v1",
  headers: { "Content-Type": "application/json" },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("agency_access_token")
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("agency_access_token")
      window.location.href = "/login"
    }
    return Promise.reject(err)
  }
)

interface LoginPayload {
  email: string
  password: string
}

export const authApi = {
  login: (payload: LoginPayload) => api.post("/auth/login", payload),
  me: () => api.get("/auth/me"),
}

export default api
