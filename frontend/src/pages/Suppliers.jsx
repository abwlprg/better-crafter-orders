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

// ── Delete confirm modal ──────────────────────────────────────────────────────

function DeleteConfirmModal({ supplier, onClose, onDeleted, adminKey }) {
  const [typed, setTyped] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const confirmed = typed.trim() === supplier.name.trim()

  const doDelete = async () => {
    if (!confirmed) return
    setDeleting(true)
    setError(null)
    try {
      const res = await apiRequest(`/suppliers/${supplier.id}`, 'DELETE', undefined, adminKey)
      setResult(res)
    } catch (e) {
      setError(e.message)
      setDeleting(false)
    }
  }

  if (result) {
    return (
      <div className="modal-overlay">
        <div className="modal delete-modal">
          <div className="modal-header">
            <h2>Supplier Deleted</h2>
          </div>
          <p style={{ marginBottom: 12, color: 'var(--muted)', fontSize: 13 }}>
            <strong>{supplier.name}</strong> has been removed from the app.
          </p>
          {result.warnings?.map((w, i) => (
            <div key={i} className="delete-warning-msg">{w}</div>
          ))}
          <div className="modal-footer">
            <button className="btn btn-primary" onClick={onDeleted} type="button">Done</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal delete-modal">
        <div className="modal-header">
          <h2>Delete Supplier</h2>
          <button className="modal-close" onClick={onClose} type="button">×</button>
        </div>

        <div className="delete-warning-msg" style={{ marginBottom: 16 }}>
          <strong>This action cannot be undone.</strong>
          <ul style={{ marginTop: 8, paddingLeft: 18, lineHeight: 1.7 }}>
            <li>The supplier <strong>{supplier.name}</strong> will be permanently removed from the app.</li>
            {supplier.sandbox_onedrive_file_id && (
              <li>The associated sandbox Word document will be deleted from OneDrive.</li>
            )}
            {!supplier.sandbox_onedrive_file_id && (
              <li>No sandbox Word document is linked — only the app record will be removed.</li>
            )}
            <li>If the sandbox document is already missing, the supplier will still be removed.</li>
            <li>Production OneDrive deletion is disabled unless explicitly enabled.</li>
          </ul>
        </div>

        {error && <div className="error-msg">{error}</div>}

        <div className="form-group">
          <label>Type the supplier name to confirm: <strong>{supplier.name}</strong></label>
          <input
            className="text-input"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={supplier.name}
            autoFocus
            autoComplete="off"
            spellCheck="false"
          />
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} type="button">Cancel</button>
          <button
            className="btn btn-danger"
            onClick={doDelete}
            disabled={!confirmed || deleting}
            type="button"
          >
            {deleting ? 'Deleting…' : 'Delete Supplier'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Add/Edit modal ────────────────────────────────────────────────────────────

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

  const handleCancel = () => {
    const dirty =
      form.name.trim() !== (supplier?.name ?? '').trim() ||
      form.email.trim() !== (supplier?.email ?? '').trim() ||
      form.onedrive_file_name.trim() !== (supplier?.onedrive_file_name ?? '').trim() ||
      form.custom_fields.some((cf) => cf.field_name.trim() !== '')
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    onClose()
  }

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <h2>{isEdit ? `Edit ${supplier.name}` : 'Add Supplier'}</h2>
          <button className="modal-close" onClick={handleCancel} type="button">×</button>
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

          <p className="cf-section-help">
            Each custom field becomes an extra column in this supplier&apos;s Word document and tells the parser where to find that value.
          </p>

          <div className="custom-field-header-row">
            <span>
              Field Name
              <span className="cf-col-sub">Column name</span>
            </span>
            <span>
              Type
              <span className="cf-col-sub">Value type</span>
            </span>
            <span>
              Source
              <span className="cf-col-sub">Where to look</span>
            </span>
            <span>
              Hint
              <span className="cf-col-sub">Label or clue</span>
            </span>
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
          <button className="btn btn-secondary" onClick={handleCancel} type="button">Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving} type="button">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Suppliers page ────────────────────────────────────────────────────────────

export default function Suppliers({ adminKey }) {
  const [suppliers, setSuppliers] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [modal, setModal] = useState(null)       // null | 'add' | supplierObj
  const [deleteTarget, setDeleteTarget] = useState(null) // null | supplierObj
  const [sandboxState, setSandboxState] = useState({})  // { [id]: { loading, result } }

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
        [supplierId]: {
          loading: false,
          result: {
            ok: true,
            action: result.action,
            file_name: result.file_name,
            columns: result.columns,
            added_columns: result.added_columns,
            warnings: result.warnings,
          },
        },
      }))
      load() // Refresh supplier list so sandbox metadata displays
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
                <div className="supplier-card-meta">
                  {s.sandbox_onedrive_file_id ? (
                    <span style={{ color: 'var(--success)' }}>
                      Sandbox Doc: Created
                      {s.sandbox_onedrive_file_name && (
                        <span style={{ color: 'var(--muted)', fontWeight: 400 }}>
                          {' '}— {s.sandbox_onedrive_file_name}
                        </span>
                      )}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--muted)' }}>Sandbox Doc: Not created</span>
                  )}
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
                      title={s.sandbox_onedrive_file_id
                        ? 'Add missing columns to existing sandbox doc (safe — preserves all rows)'
                        : 'Create a sandbox Word document for this supplier'}
                    >
                      {ss.loading
                        ? (s.sandbox_onedrive_file_id ? 'Updating…' : 'Creating…')
                        : (s.sandbox_onedrive_file_id ? 'Update Sandbox Doc' : 'Create Sandbox Doc')}
                    </button>
                  )}
                  <button
                    className="btn btn-ghost btn-sm btn-delete-supplier"
                    onClick={() => setDeleteTarget(s)}
                    disabled={!adminKey}
                    type="button"
                    title="Permanently delete this supplier"
                  >
                    Delete
                  </button>
                </div>
                {ss.result && (
                  <div style={{ marginTop: 8 }}>
                    {ss.result.ok ? (
                      <div className="sandbox-ok-msg">
                        {ss.result.action === 'created' && <>Sandbox doc created: <strong>{ss.result.file_name}</strong></>}
                        {ss.result.action === 'updated' && (
                          ss.result.added_columns?.length > 0
                            ? <>Updated: added columns <strong>{ss.result.added_columns.join(', ')}</strong></>
                            : <>Up to date — no new columns needed.</>
                        )}
                        {ss.result.action === 'attached_and_updated' && <>Attached to existing file: <strong>{ss.result.file_name}</strong></>}
                        {ss.result.warnings?.map((w, i) => (
                          <div key={i} style={{ marginTop: 4, opacity: 0.8, fontSize: 11 }}>{w}</div>
                        ))}
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

      {deleteTarget && (
        <DeleteConfirmModal
          supplier={deleteTarget}
          adminKey={adminKey}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => { setDeleteTarget(null); load() }}
        />
      )}
    </div>
  )
}
