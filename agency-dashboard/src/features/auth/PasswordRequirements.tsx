import { PASSWORD_REQUIREMENTS } from '../../lib/passwordValidation'

export default function PasswordRequirements({ password }: { password: string }) {
  if (!password) return null
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: '-6px 0 14px', display: 'grid', gap: 3 }}>
      {PASSWORD_REQUIREMENTS.map((r) => {
        const ok = r.test(password)
        return (
          <li
            key={r.label}
            style={{
              fontSize: 11,
              color: ok ? 'var(--green)' : 'var(--text-dim)',
            }}
          >
            {ok ? '✓' : '·'} {r.label}
          </li>
        )
      })}
    </ul>
  )
}
