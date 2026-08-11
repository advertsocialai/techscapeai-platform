import { useMemo } from 'react'

// ── Strength scoring ─────────────────────────────────
// Simple, dependency-free heuristic (no zxcvbn needed). Scores 0-4.
export type StrengthLevel = 0 | 1 | 2 | 3 | 4

export interface StrengthResult {
  score: StrengthLevel
  label: string
  color: string
  hint: string
}

const LEVELS: { label: string; color: string; hint: string }[] = [
  { label: 'Too weak',  color: '#F87171', hint: 'At least 8 characters' },
  { label: 'Weak',      color: '#F87171', hint: 'Add a number and a symbol' },
  { label: 'Fair',      color: '#F7A97C', hint: 'Add an uppercase letter' },
  { label: 'Strong',    color: '#3B8FE8', hint: 'Looks good' },
  { label: 'Very strong', color: '#34D399', hint: 'Great password' },
]

export function scorePassword(pw: string): StrengthResult {
  if (!pw) return { score: 0, label: '', color: 'rgba(255,255,255,0.1)', hint: '' }

  let score = 0
  const hasLower = /[a-z]/.test(pw)
  const hasUpper = /[A-Z]/.test(pw)
  const hasDigit = /\d/.test(pw)
  const hasSymbol = /[^A-Za-z0-9]/.test(pw)
  const varietyCount = [hasLower, hasUpper, hasDigit, hasSymbol].filter(Boolean).length

  if (pw.length >= 8) score += 1
  if (pw.length >= 12) score += 1
  if (varietyCount >= 3) score += 1
  if (varietyCount === 4 && pw.length >= 10) score += 1

  // Penalize common weak patterns
  const lower = pw.toLowerCase()
  const commonPatterns = ['password', '12345678', 'qwerty', 'letmein', 'admin']
  if (commonPatterns.some(p => lower.includes(p))) score = Math.max(0, score - 2)
  if (pw.length < 8) score = 0

  const clamped = Math.min(4, Math.max(0, score)) as StrengthLevel
  return { score: clamped, ...LEVELS[clamped] }
}

// ── Component ─────────────────────────────────────────
interface PasswordStrengthProps {
  password: string
}

export default function PasswordStrength({ password }: PasswordStrengthProps) {
  const result = useMemo(() => scorePassword(password), [password])

  if (!password) return null

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 5 }}>
        {[0, 1, 2, 3].map(i => (
          <div
            key={i}
            style={{
              flex: 1,
              height: 3,
              borderRadius: 2,
              background: i < result.score ? result.color : 'rgba(255,255,255,0.1)',
              transition: 'background 0.2s ease',
            }}
          />
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: result.color }}>{result.label}</span>
        <span style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.32)' }}>{result.hint}</span>
      </div>
    </div>
  )
}

// ── Usage ─────────────────────────────────────────────
// Drop this under any password <input>, matching the LoginPage/AddressPage
// input pattern:
//
//   const [password, setPassword] = useState('')
//   ...
//   <input type="password" value={password} onChange={e => setPassword(e.target.value)} ... />
//   <PasswordStrength password={password} />
//
// To block submit on weak passwords, reuse scorePassword() in your validate():
//   if (scorePassword(password).score < 2) e.password = 'Choose a stronger password'
