import axios from "axios"

const travelApi = axios.create({
  baseURL: import.meta.env.VITE_TRAVEL_API_URL || "http://localhost:8000/api/travel/v1",
  headers: { "Content-Type": "application/json" },
})

travelApi.interceptors.request.use((config) => {
  const token = localStorage.getItem("agency_access_token")
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export interface WikiEntry {
  id: string
  title: string
  category: string
  content: string
}

export const wikiApi = {
  list: (category?: string) =>
    travelApi.get("/wiki", { params: category ? { category } : {} }),
  create: (payload: Partial<WikiEntry>) => travelApi.post("/wiki", payload),
  bulkCreate: (entries: Partial<WikiEntry>[]) => travelApi.post("/wiki/bulk", entries),
  search: (query: string, category?: string, limit = 8) =>
    travelApi.post("/wiki/search", { query, category, limit }),
  delete: (id: string) => travelApi.delete(`/wiki/${id}`),
}

export default travelApi
