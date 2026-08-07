import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { playbooksApi } from '../../lib/api'

export default function PlaybooksPage() {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null)

  const { data: playbooks, isLoading, isError } = useQuery({
    queryKey: ['playbooks'],
    queryFn: () => playbooksApi.list(),
  })

  const renderMutation = useMutation({
    mutationFn: (ucId: string) => playbooksApi.render(ucId, {}),
    onSuccess: (data) => setPreview(data as Record<string, unknown>),
  })

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">AI Playbook</div>
          <div className="page-sub">{playbooks?.length ?? 0} automated use cases (TravelWorkflow OS)</div>
        </div>
      </div>
      <div className="content">
        {isLoading && <div className="loading-block">Loading…</div>}
        {isError && <div className="error-banner">Could not load playbooks.</div>}
        {!isLoading && !isError && (
          <div style={{ display: 'grid', gap: 8 }}>
            {(playbooks ?? []).map((pb) => (
              <div key={pb.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span className="badge blue" style={{ fontFamily: 'monospace' }}>{pb.id}</span>
                      <span className="t2">{pb.title}</span>
                    </div>
                    <div className="t3">{pb.category} · SLA {pb.sla} · {pb.channels.join(', ')}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      className="btn ghost"
                      onClick={() => setExpanded(expanded === pb.id ? null : pb.id)}
                    >
                      {expanded === pb.id ? 'Hide' : 'Details'}
                    </button>
                    <button
                      className="btn primary"
                      onClick={() => renderMutation.mutate(pb.id)}
                      disabled={renderMutation.isPending}
                    >
                      Preview render
                    </button>
                  </div>
                </div>
                {expanded === pb.id && (
                  <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--text-dim)' }}>
                    {pb.trigger}
                  </div>
                )}
                {preview && renderMutation.variables === pb.id && (
                  <pre style={{ marginTop: 10, padding: 10, background: 'rgba(0,0,0,0.4)', borderRadius: 8, fontSize: 11, overflowX: 'auto' }}>
                    {JSON.stringify(preview, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
