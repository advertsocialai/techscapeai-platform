// ── Klara Logo ──────────────────────────────────────
export default function KlaraLogo() {
  return (
    <div style={{
      width: 68, height: 68, borderRadius: 22,
      background: 'rgba(255,255,255,0.07)',
      border: '1.5px solid rgba(255,255,255,0.12)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 0 40px rgba(59,143,232,0.12)',
    }}>
      <svg width="38" height="30" viewBox="0 0 167 134" fill="none">
        <path d="M166 32C166 49 152 63 134 63C117 63 103 49 103 32C103 14 117 0 134 0C152 0 166 14 166 32Z" fill="#2D7DD2"/>
        <path d="M134 70C152 70 166 85 166 102C166 119 153 133 136 134H70C65 134 62 128 66 124L112 80C117 74 126 70 134 70Z" fill="rgba(255,255,255,0.95)"/>
        <path d="M0 102C0 85 14 70 32 70C49 70 63 85 63 102C63 120 49 134 32 134C14 134 0 120 0 102Z" fill="#F7A97C"/>
        <path d="M32 63C14 63 0 49 0 32C0 15 13 1 30 0H96C101 0 104 6 100 10L55 54C49 60 41 63 32 63Z" fill="rgba(255,255,255,0.95)"/>
      </svg>
    </div>
  )
}
