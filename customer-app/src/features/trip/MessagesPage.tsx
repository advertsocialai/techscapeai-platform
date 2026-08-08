/**
 * Traveller — messages.
 *
 * 💬 The composer is DISABLED, and says why. There is no traveller→agency
 * inbound channel on the backend: the WhatsApp integration is outbound-only,
 * which is also why the 24-hour session window is tracked in an in-process dict
 * (DEBT-10).
 *
 * The tempting alternative — accept the text, show it in the thread, and let it
 * vanish — is the exact failure this codebase keeps guarding against. A
 * customer who believes they told their agent about a visa problem, and did
 * not, is worse off than one who was told the channel is unavailable.
 */
import { useQuery } from '@tanstack/react-query'

import { travellerApi } from '../../lib/travellerApi'
import { colors, radii } from '../../styles/tokens'
import { EmptyBlock, ErrorBlock, SkeletonBlock } from './ui'

export default function MessagesPage() {
  const messagesQ = useQuery({
    queryKey: ['traveller', 'messages'],
    queryFn: travellerApi.messages,
  })

  if (messagesQ.isLoading) return <SkeletonBlock rows={3} />
  if (messagesQ.isError) {
    return <ErrorBlock error={messagesQ.error} onRetry={() => messagesQ.refetch()} />
  }

  const messages = messagesQ.data ?? []

  return (
    <>
      {messages.length === 0 ? (
        <EmptyBlock
          title="No messages"
          reason="Your agent hasn't sent anything yet."
        />
      ) : (
        <div style={{ display: 'grid', gap: 10, marginBottom: 14 }}>
          {messages.map((m) => {
            const mine = m.from === 'you'
            return (
              <div
                key={m.id}
                style={{
                  alignSelf: mine ? 'flex-end' : 'flex-start',
                  justifySelf: mine ? 'end' : 'start',
                  maxWidth: '82%',
                  background: mine ? colors.blueDim : colors.surface,
                  border: `1px solid ${mine ? colors.blueBorder : colors.surfaceBorder}`,
                  borderRadius: 18,
                  padding: '11px 14px',
                }}
              >
                <div style={{ fontSize: 13, lineHeight: 1.5 }}>{m.text}</div>
                <div style={{ fontSize: 10, color: colors.textLabel, marginTop: 5 }}>
                  {new Date(m.at).toLocaleString()}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Disabled composer with the reason attached. */}
      <div
        style={{
          background: colors.surface,
          border: `1px solid ${colors.surfaceBorder}`,
          borderRadius: radii.card,
          padding: '16px 16px',
        }}
      >
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            disabled
            placeholder="Replying isn't available yet"
            style={{
              flex: 1,
              background: colors.inputBg,
              border: `1px solid ${colors.inputBorder}`,
              borderRadius: radii.input,
              padding: '12px 14px',
              color: colors.textSecondary,
              fontSize: 13,
              opacity: 0.6,
            }}
          />
          <button
            type="button"
            disabled
            style={{
              background: colors.inputBg,
              border: `1px solid ${colors.inputBorder}`,
              borderRadius: radii.input,
              padding: '0 18px',
              color: colors.textLabel,
              fontSize: 13,
              fontWeight: 600,
              cursor: 'not-allowed',
            }}
          >
            Send
          </button>
        </div>
        <div style={{ fontSize: 11, color: colors.textSecondary, lineHeight: 1.5, marginTop: 10 }}>
          There is no traveller-to-agency channel on the backend yet — messaging is outbound only.
          Contact your agent directly for now. Accepting a message here and dropping it would be
          worse than saying so.
        </div>
      </div>
    </>
  )
}
