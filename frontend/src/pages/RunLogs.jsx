import { useEffect, useState } from 'react'
import { API_URL } from '../config'

const fmtTimestamp = (ts) => {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return ts
  }
}

export default function RunLogs({ adminKey }) {
  const [logs, setLogs] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    if (!adminKey) {
      return
    }
    setLoading(true)
    setError(null)
    fetch(`${API_URL}/run-logs`, { headers: { 'X-Admin-API-Key': adminKey } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => setLogs(d.run_logs || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!adminKey) return undefined
    let cancelled = false
    fetch(`${API_URL}/run-logs`, { headers: { 'X-Admin-API-Key': adminKey } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => {
        if (!cancelled) setLogs(d.run_logs || [])
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [adminKey])

  return (
    <div>
      <div className="top-bar">
        <h1>Run Logs</h1>
        <button className="btn btn-secondary" onClick={load} disabled={!adminKey || loading} type="button">
          Refresh
        </button>
      </div>

      {!adminKey && <div className="error-msg">Enter your admin key in the sidebar to view run logs.</div>}
      {error && <div className="error-msg">{error}</div>}
      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {logs && logs.length === 0 && (
        <div className="empty-state">No run logs yet. Run a Fetch Orders dry-run to create entries.</div>
      )}

      {logs && logs.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Suppliers</th>
                <th>Date range</th>
                <th>Emails</th>
                <th>Parsed</th>
                <th>Written</th>
                <th>Skipped</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => (
                <tr key={i}>
                  <td className="mono" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                    {fmtTimestamp(log.timestamp)}
                  </td>
                  <td>{(log.supplier_ids || []).join(', ')}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{log.date_range}</td>
                  <td style={{ textAlign: 'center' }}>{log.emails_found ?? '—'}</td>
                  <td style={{ textAlign: 'center' }}>{log.orders_parsed ?? '—'}</td>
                  <td style={{ textAlign: 'center' }}>{log.orders_written ?? '—'}</td>
                  <td style={{ textAlign: 'center' }}>{log.orders_skipped ?? '—'}</td>
                  <td>
                    <span className={`badge ${log.dry_run ? 'badge-blue' : 'badge-yellow'}`}>
                      {log.dry_run ? 'dry-run' : 'write'}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${log.status === 'ok' ? 'badge-green' : 'badge-red'}`}>
                      {log.status}
                    </span>
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--danger)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.error || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
