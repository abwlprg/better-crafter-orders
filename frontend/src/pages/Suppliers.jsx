import { useEffect, useState } from 'react'
import { API_URL } from '../config'

const EMPTY_FIELD = { field_name: '', type: 'text', source: 'body', hint: '' }

const EMPTY_FORM = {
  id: '', name: '', email: '', status: 'active',
  onedrive_file_name: '', onedrive_file_id: '', onedrive_drive_id: '',
  parser_type: 'stephen_regex', custom_fields: [{ ...EMPTY_FIELD }],
}

function initFields(fields) {
  if (!fields || fields.length === 0) return [{ ...EMPTY_FIELD }]
  return fields.map((f) => ({ ...EMPTY_FIELD, ...f }))
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
  const [form, setForm] = useState(
    isEdit
      ? { ...supplier, custom_fields: initFields(supplier.custom_fields) }
      : { ...EMPTY_FORM, custom_fields: [{ ...EMPTY_FIELD }] }
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }))

  const addField = () =>
    setForm((f) => ({ ...f, custom_fields: [...f.custom_fields, { ...EMPTY_FIELD }] }))

  const removeField = (idx) =>
    setForm((f) => ({ ...f, custom_fields: f.custom_fields.filter((_, i) => i !== idx) }))

  const updateField = (idx, key, val) =>
    setForm((f) => ({
      ...f,
      custom_fields: f.custom_fields.map((cf, i) => (i === idx ? { ...cf, [key]: val } : cf)),
    }))

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const payload = {
        ...form,
        custom_fields: form.custom_fields.filter((cf) => cf.field_name.trim() !== ''),
      }
      if (isEdit) {
        const body = { ...payload }
        delete body.id
        await apiRequest(`/suppliers/${supplier.id}`, 'PUT', body, adminKey)
      } else {
        await apiRequest('/suppliers', 'POST', payload, adminKey)
      }
      onSaved()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const hasMultipleFields = form.custom_fields.length > 1

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
          <label>Supplier Name</label>
          <input
            className="text-input"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Display name"
          />
        </div>

        <div className="form-group">
          <label>Status</label>
          <select className="select-input" value={form.status} onChange={(e) => set('status', e.target.value)}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        <div className="form-group">
          <label>To: Email Address / Routing Key</label>
          <input
            className="text-input"
            value={form.email}
            onChange={(e) => set('email', e.target.value)}
            placeholder="supplier@example.com"
          />
        </div>

        <div className="form-group">
          <label>OneDrive File Name</label>
          <input
            className="text-input"
            value={form.onedrive_file_name}
            onChange={(e) => set('onedrive_file_name', e.target.value)}
            placeholder="Supplier Name 2026"
          />
        </div>

        <div className="form-section">
          <div className="form-section-header">
            <span className="form-section-title">Custom Fields</span>
            <button className="btn btn-secondary btn-sm" onClick={addField} type="button">
              + Add Field
            </button>
          </div>

          <div className="custom-field-header-row">
            <span>Field Name</span>
            <span>Type</span>
            <span>Source</span>
            <span>Hint</span>
            <span />
          </div>

          {form.custom_fields.map((cf, idx) => (
            <div key={idx} className="custom-field-row">
              <input
                className="text-input"
                placeholder="e.g. Order number"
                value={cf.field_name}
                onChange={(e) => updateField(idx, 'field_name', e.target.value)}
              />
              <select
                className="select-input"
                value={cf.type}
                onChange={(e) => updateField(idx, 'type', e.target.value)}
              >
                <option value="text">Text</option>
                <option value="number">Number</option>
                <option value="date">Date</option>
                <option value="boolean">Boolean</option>
              </select>
              <select
                className="select-input"
                value={cf.source}
                onChange={(e) => updateField(idx, 'source', e.target.value)}
              >
                <option value="body">Body</option>
                <option value="subject">Subject</option>
                <option value="pdf">PDF</option>
                <option value="header">Header</option>
                <option value="manual">Manual</option>
              </select>
              <input
                className="text-input"
                placeholder='e.g. "Brand:"'
                value={cf.hint}
                onChange={(e) => updateField(idx, 'hint', e.target.value)}
              />
              {hasMultipleFields ? (
                <button
                  className="btn btn-ghost btn-sm custom-field-remove"
                  onClick={() => removeField(idx)}
                  type="button"
                  title="Remove field"
                >
                  ✕
                </button>
              ) : (
                <span />
              )}
            </div>
          ))}
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
  const [sandboxState, setSandboxState] = useState({}) // { [id]: { loading, result } }

  const load = () => {
    if (!adminKey) return
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
      .then((data) => { if (!cancelled) setSuppliers(data.suppliers || []) })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
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

  const createSandboxDoc = async (supplierId) => {
    setSandboxState((s) => ({ ...s, [supplierId]: { loading: true, result: null } }))
    try {
      const result = await apiRequest(
        `/suppliers/${supplierId}/create-sandbox-docx`,
        'POST',
        undefined,
        adminKey,
      )
      setSandboxState((s) => ({
        ...s,
        [supplierId]: { loading: false, result: { ok: true, file_name: result.file_name, columns: result.columns } },
      }))
    } catch (e) {
      setSandboxState((s) => ({
        ...s,
        [supplierId]: { loading: false, result: { ok: false, error: e.message } },
      }))
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
          {suppliers.map((s) => {
            const ss = sandboxState[s.id] || {}
            return (
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
                {s.onedrive_file_name && (
                  <div className="supplier-card-meta">File: {s.onedrive_file_name}</div>
                )}
                <div className="supplier-card-meta">
                  Custom fields: <strong>{s.custom_fields?.length ?? 0}</strong>
                </div>
                <div className="supplier-card-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => setModal(s)} type="button">Edit</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => toggleStatus(s)} type="button">
                    {s.status === 'active' ? 'Deactivate' : 'Activate'}
                  </button>
                  {s.onedrive_file_name && (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => createSandboxDoc(s.id)}
                      disabled={ss.loading || !adminKey}
                      type="button"
                      title="Create a test Word document in the OneDrive sandbox folder"
                    >
                      {ss.loading ? 'Creating…' : '[Test] Create Doc'}
                    </button>
                  )}
                </div>
                {ss.result && (
                  <div style={{ marginTop: 8 }}>
                    {ss.result.ok ? (
                      <div className="sandbox-ok-msg">
                        Sandbox doc created: <strong>{ss.result.file_name}</strong>
                        {ss.result.columns && (
                          <div style={{ marginTop: 4, opacity: 0.85 }}>
                            Columns: {ss.result.columns.join(', ')}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="error-msg">{ss.result.error}</div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
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
