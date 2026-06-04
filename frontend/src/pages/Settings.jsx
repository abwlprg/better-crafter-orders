import { useEffect, useState } from 'react'
import { API_URL } from '../config'

function StatusBadge({ value }) {
  if (value === true)  return <span className="badge badge-green">present</span>
  if (value === false) return <span className="badge badge-red">missing</span>
  if (typeof value === 'string') return <span className="badge badge-blue">{value}</span>
  return <span className="badge badge-grey">—</span>
}

export default function Settings({ adminKey }) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!adminKey) {
      return
    }
    fetch(`${API_URL}/config-status`, {
      headers: { 'X-Admin-API-Key': adminKey },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStatus)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [adminKey])

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
        <p>Configuration status only — raw secrets are never shown in the browser.</p>
      </div>

      {!adminKey && <div className="error-msg">Enter your admin key in the sidebar to view configuration status.</div>}
      {loading && adminKey && <p style={{ color: 'var(--muted)' }}>Loading config status…</p>}
      {error && <div className="error-msg">{error}</div>}

      {status && (
        <div className="config-grid">
          {/* Local app */}
          <div className="config-group">
            <div className="config-group-title">Local app</div>
            {Object.entries(status.local || {}).map(([k, v]) => (
              <div className="config-row" key={k}>
                <span className="config-key">{k.replace(/_/g, ' ')}</span>
                <StatusBadge value={v} />
              </div>
            ))}
          </div>

          {/* Admin key */}
          <div className="config-group">
            <div className="config-group-title">Admin</div>
            <div className="config-row">
              <span className="config-key">ADMIN_API_KEY</span>
              <StatusBadge value={status.admin_api_key} />
            </div>
          </div>

          {/* Gmail */}
          <div className="config-group">
            <div className="config-group-title">Gmail</div>
            {Object.entries(status.gmail || {}).map(([k, v]) => (
              <div className="config-row" key={k}>
                <span className="config-key">{k.replace(/_/g, ' ')}</span>
                <StatusBadge value={v} />
              </div>
            ))}
          </div>

          {/* OneDrive */}
          <div className="config-group">
            <div className="config-group-title">OneDrive</div>
            {Object.entries(status.onedrive || {}).map(([k, v]) => (
              <div className="config-row" key={k}>
                <span className="config-key" style={{ fontSize: 11 }}>{k.replace(/_/g, ' ')}</span>
                <StatusBadge value={v} />
              </div>
            ))}
          </div>

          {/* Production-later */}
          <div className="config-group">
            <div className="config-group-title">Production later</div>
            {Object.entries(status.production_later || {}).map(([k, v]) => (
              <div className="config-row" key={k}>
                <span className="config-key" style={{ fontSize: 11 }}>{k.replace(/_/g, ' ')}</span>
                <StatusBadge value={v} />
              </div>
            ))}
          </div>

          {/* Legacy/reference */}
          <div className="config-group">
            <div className="config-group-title">Legacy reference</div>
            {Object.entries(status.legacy_reference || {}).map(([k, v]) => (
              <div className="config-row" key={k}>
                <span className="config-key" style={{ fontSize: 11 }}>{k.replace(/_/g, ' ')}</span>
                <StatusBadge value={v} />
              </div>
            ))}
          </div>

          {/* Gemini */}
          <div className="config-group">
            <div className="config-group-title">Gemini</div>
            {Object.entries(status.gemini || {}).map(([k, v]) => (
              <div className="config-row" key={k}>
                <span className="config-key">{k.replace(/_/g, ' ')}</span>
                <StatusBadge value={v} />
              </div>
            ))}
            <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>
              Gemini is paused — billing/quota not yet confirmed. Stephen regex fallback is active.
            </p>
          </div>
        </div>
      )}

      <div className="section" style={{ marginTop: 28 }}>
        <div className="section-title">Production write guard</div>
        <div className="config-group" style={{ maxWidth: 480 }}>
          <div className="config-row">
            <span className="config-key">Production OneDrive writes</span>
            <span className="badge badge-red">disabled</span>
          </div>
          <div className="config-row">
            <span className="config-key">Sandbox writes (ONEDRIVE_TEST_*)</span>
            <StatusBadge value={status?.onedrive?.sandbox_write_enabled} />
          </div>
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>
            Production writes stay disabled until safeguards #11–#15 are implemented and validated.
          </p>
        </div>
      </div>
    </div>
  )
}
