import { useEffect, useState } from 'react'
import { API_URL } from '../config'

const EMPTY_FORM = {
  id: '', name: '', email: '', status: 'active',
  onedrive_file_name: '', onedrive_file_id: '', onedrive_drive_id: '',
  parser_type: 'stephen_regex', custom_fields: [],
}

async function apiRequest(path, method, body, adminKey) {
  const r = await fetch(`${API_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Admin-API-Key': adminKey },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    const payload = await r.json().catch(() => ({}))
    throw new Error(payload?.detail || `HTTP ${r.status}`)
  }
  return r.json()
}

function SupplierModal({ supplier, onClose, onSaved, adminKey }) {
  const isEdit = Boolean(supplier)
  const [form, setForm] = useState(isEdit ? { ...supplier } : { ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }))

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      if (isEdit) {
        const body = { ...form }
        delete body.id
        await apiRequest(`/suppliers/${supplier.id}`, 'PUT', body, adminKey)
      } else {
        await apiRequest('/suppliers', 'POST', form, adminKey)
      }
      onSaved()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <h2>{isEdit ? `Edit ${supplier.name}` : 'Add Supplier'}</h2>
          <button className="modal-close" onClick={onClose} type="button">×</button>
        </div>

        {error && <div className="error-msg">{error}</div>}

        <div className="form-group">
          <label>Supplier ID</label>
          <input
            className="text-input"
            value={form.id}
            onChange={(e) => set('id', e.target.value)}
            disabled={isEdit}
            placeholder="e.g. steven"
          />
        </div>

        <div className="form-group">
          <label>Name</label>
          <input className="text-input" value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="Display name" />
        </div>

        <div className="form-group">
          <label>Email (routing key)</label>
          <input className="text-input" value={form.email} onChange={(e) => set('email', e.target.value)} placeholder="supplier@example.com" />
        </div>

        <div className="form-group">
          <label>Status</label>
          <select className="select-input" value={form.status} onChange={(e) => set('status', e.target.value)}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        <div className="form-group">
          <label>Parser type</label>
          <select className="select-input" value={form.parser_type} onChange={(e) => set('parser_type', e.target.value)}>
            <option value="stephen_regex">Stephen Regex</option>
            <option value="smart">Smart (Gemini + fallback)</option>
          </select>
        </div>

        <div className="form-group">
          <label>OneDrive file name</label>
          <input className="text-input" value={form.onedrive_file_name} onChange={(e) => set('onedrive_file_name', e.target.value)} placeholder="Orders.docx" />
        </div>

        <div className="form-group">
          <label>OneDrive file ID</label>
          <input className="text-input" value={form.onedrive_file_id} onChange={(e) => set('onedrive_file_id', e.target.value)} placeholder="Leave blank until production" />
        </div>

        <div className="form-group">
          <label>OneDrive drive ID</label>
          <input className="text-input" value={form.onedrive_drive_id} onChange={(e) => set('onedrive_drive_id', e.target.value)} placeholder="Leave blank until production" />
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} type="button">Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving} type="button">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Suppliers({ adminKey }) {
  const [suppliers, setSuppliers] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [modal, setModal] = useState(null) // null | 'add' | supplierObj

  const load = () => {
    if (!adminKey) {
      return
    }
    setLoading(true)
    setError(null)
    fetch(`${API_URL}/suppliers`, { headers: { 'X-Admin-API-Key': adminKey } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => setSuppliers(data.suppliers || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!adminKey) return undefined
    let cancelled = false
    fetch(`${API_URL}/suppliers`, { headers: { 'X-Admin-API-Key': adminKey } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => {
        if (!cancelled) setSuppliers(data.suppliers || [])
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [adminKey])

  const toggleStatus = async (supplier) => {
    const newStatus = supplier.status === 'active' ? 'inactive' : 'active'
    try {
      await apiRequest(`/suppliers/${supplier.id}`, 'PATCH', { status: newStatus }, adminKey)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <div className="top-bar">
        <h1>Suppliers</h1>
        <button className="btn btn-primary" onClick={() => setModal('add')} disabled={!adminKey} type="button">
          + Add Supplier
        </button>
      </div>

      {!adminKey && <div className="error-msg">Enter your admin key in the sidebar to manage suppliers.</div>}
      {error && <div className="error-msg">{error}</div>}
      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {suppliers && (
        <div className="supplier-list">
          {suppliers.map((s) => (
            <div className="supplier-card" key={s.id}>
              <div className="supplier-card-header">
                <div>
                  <div className="supplier-card-name">{s.name}</div>
                  <div className="supplier-card-id">{s.id}</div>
                </div>
                <span className={`badge ${s.status === 'active' ? 'badge-green' : 'badge-grey'}`}>
                  {s.status}
                </span>
              </div>
              <div className="supplier-card-meta">
                Email: {s.email || <span style={{ color: 'var(--muted)' }}>not set</span>}
              </div>
              <div className="supplier-card-meta">Parser: {s.parser_type}</div>
              {s.onedrive_file_name && (
                <div className="supplier-card-meta">File: {s.onedrive_file_name}</div>
              )}
              <div className="supplier-card-actions">
                <button className="btn btn-ghost btn-sm" onClick={() => setModal(s)} type="button">Edit</button>
                <button className="btn btn-ghost btn-sm" onClick={() => toggleStatus(s)} type="button">
                  {s.status === 'active' ? 'Deactivate' : 'Activate'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {suppliers?.length === 0 && (
        <div className="empty-state">No suppliers configured yet.</div>
      )}

      {modal && (
        <SupplierModal
          supplier={modal === 'add' ? null : modal}
          adminKey={adminKey}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load() }}
        />
      )}
    </div>
  )
}
