import { PASSWORD_REQUIREMENTS } from '../../lib/passwordValidation'

/**
 * Live checklist of the server's password rules.
 *
 * The point is WHEN it appears, not that it looks nice: the password is only
 * transmitted on the final screen of signup, so without this the first time a
 * user learns their password is unacceptable is four screens and ~14 fields
 * later. Showing the rules as they type moves that discovery to keystroke one.
 *
 * Styled inline to match the onboarding glass cards — this app has no CSS
 * variable layer (agency-dashboard's equivalent component uses `var(--green)`).
 */
export default function PasswordRequirements({ password }: { password: string }) {
  if (!password) return null
  return (
    <ul
      style={{
        listStyle: 'none',
        padding: 0,
        margin: '6px 0 0',
        display: 'grid',
        gap: 3,
      }}
    >
      {PASSWORD_REQUIREMENTS.map((r) => {
        const ok = r.test(password)
        return (
          <li
            key={r.label}
            style={{
              fontSize: 10.5,
              color: ok ? '#34D399' : 'rgba(255,255,255,0.32)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span aria-hidden style={{ width: 9, display: 'inline-block' }}>{ok ? '✓' : '·'}</span>
            {r.label}
          </li>
        )
      })}
    </ul>
  )
}
