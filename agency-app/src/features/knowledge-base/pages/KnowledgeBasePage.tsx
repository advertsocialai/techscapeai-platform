import { useEffect, useState } from "react"
import { wikiApi } from "../../../lib/wikiApi"

const CATEGORY_LABELS = {
  destination: "Destination",
  package: "Package",
  policy: "Policy",
  sop: "SOP",
  objection: "Objection Handling",
  supplier: "Supplier",
  pricing: "Pricing",
  general: "General",
}

export default function KnowledgeBasePage() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("")

  useEffect(() => {
    loadEntries()
  }, [categoryFilter])

  async function loadEntries() {
    setLoading(true)
    setError("")
    try {
      const res = await wikiApi.list(categoryFilter || undefined)
      setEntries(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load knowledge base")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 24, fontFamily: "Outfit, sans-serif", background: "#0F1117", minHeight: "100vh", color: "#fff" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Knowledge Base</h1>
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", marginTop: 4 }}>
          {entries.length} entries loaded
        </p>
      </div>

      <div style={{ marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          onClick={() => setCategoryFilter("")}
          style={{
            padding: "6px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: "pointer",
            background: categoryFilter === "" ? "#10B981" : "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)", color: "#fff",
          }}
        >
          All
        </button>
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setCategoryFilter(key)}
            style={{
              padding: "6px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: "pointer",
              background: categoryFilter === key ? "#10B981" : "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)", color: "#fff",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 13 }}>Loading...</div>}
      {error && <div style={{ color: "#EF4444", fontSize: 13 }}>{error}</div>}

      {!loading && !error && entries.length === 0 && (
        <div style={{ padding: 32, textAlign: "center", color: "rgba(255,255,255,0.3)", fontSize: 13 }}>
          No entries yet. Create your first Knowledge Base entry.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {entries.map((entry) => (
          <div
            key={entry.id}
            style={{
              background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 10, padding: 14,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>{entry.title}</span>
              <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)" }}>
                {CATEGORY_LABELS[entry.category] || entry.category}
              </span>
            </div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>
              {entry.content.slice(0, 160)}{entry.content.length > 160 ? "..." : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
