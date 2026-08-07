export default function LiveCallPage() {
  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Live Call</div>
          <div className="page-sub">Real-time voice monitoring</div>
        </div>
      </div>
      <div className="content">
        <div className="card">
          <div className="empty-state">
            <div className="icon">📞</div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Not configured</div>
            <div style={{ fontSize: 12, maxWidth: 420, margin: '0 auto' }}>
              Live call monitoring and transcripts require a two-way conversational
              voice pipeline (Twilio Media Streams + Deepgram STT + ElevenLabs TTS)
              that isn't wired up yet. Today, GoGaga's Twilio integration only
              supports one-way outbound voice blasts via the playbook automations
              — see the AI Playbook screen for what's actually live.
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
