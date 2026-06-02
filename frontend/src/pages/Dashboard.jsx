import { useEffect, useState } from 'react'
import { API_URL } from '../config'

export default function Dashboard({ adminKey, navigate }) {
  const [suppliers, setSuppliers] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!adminKey) return
    fetch(`${API_URL}/suppliers`, {
      headers: { 'X-Admin-API-Key': adminKey },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => setSuppliers(data.suppliers || []))
      .catch((e) => setError(e.message))
  }, [adminKey])

  const total    = suppliers?.length ?? 0
  const active   = suppliers?.filter((s) => s.status === 'active').length ?? 0
  const withEmail = suppliers?.filter((s) => s.email).length ?? 0
  const customFieldCount = suppliers?.reduce((acc, s) => acc + (s.custom_fields?.length ?? 0), 0) ?? 0

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>System overview for Better Crafter Orders</p>
      </div>

      {!adminKey && (
        <div className="error-msg">Enter your admin key in the sidebar to load live data.</div>
      )}

      {error && <div className="error-msg">Failed to load suppliers: {error}</div>}

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-number">{total}</span>
          <span className="stat-label">Total Suppliers</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{active}</span>
          <span className="stat-label">Active Suppliers</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{withEmail}</span>
          <span className="stat-label">Configured (email)</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{customFieldCount}</span>
          <span className="stat-label">Custom Fields</span>
        </div>
      </div>

      <div className="section">
        <div className="section-title">Quick actions</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-primary" onClick={() => navigate('fetch-orders')} type="button">
            Fetch Orders
          </button>
          <button className="btn btn-secondary" onClick={() => navigate('suppliers')} type="button">
            Manage Suppliers
          </button>
          <button className="btn btn-secondary" onClick={() => navigate('run-logs')} type="button">
            View Run Logs
          </button>
        </div>
      </div>

      {suppliers && (
        <div className="section">
          <div className="section-title">Supplier summary</div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Email</th>
                  <th>Parser</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((s) => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 600 }}>{s.name}</td>
                    <td className="mono">{s.id}</td>
                    <td>
                      <span className={`badge ${s.status === 'active' ? 'badge-green' : 'badge-grey'}`}>
                        {s.status}
                      </span>
                    </td>
                    <td className="mono">{s.email || <span style={{ color: 'var(--muted)' }}>—</span>}</td>
                    <td>{s.parser_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="section">
        <div className="section-title">Production write guard</div>
        <div className="error-msg" style={{ color: 'var(--warning)', borderColor: 'rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.08)' }}>
          Production OneDrive writes are disabled until safeguards #11–#15 are complete and validated.
          Dry-run mode only.
        </div>
      </div>
    </div>
  )
}
