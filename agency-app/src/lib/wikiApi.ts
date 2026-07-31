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

export const wikiApi = {
  list: (category) =>
    travelApi.get("/wiki", { params: category ? { category } : {} }),
  create: (payload) => travelApi.post("/wiki", payload),
  bulkCreate: (entries) => travelApi.post("/wiki/bulk", entries),
  search: (query, category, limit = 8) =>
    travelApi.post("/wiki/search", { query, category, limit }),
  delete: (id) => travelApi.delete(`/wiki/${id}`),
}

export default travelApi
