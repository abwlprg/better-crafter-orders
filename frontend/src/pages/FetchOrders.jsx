import { useEffect, useState } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { API_URL } from '../config'

const MAX_PREVIEW_ROWS = 100

const PREVIEW_COLUMNS = [
  'supplier_id', 'supplier_name', 'order_date', 'item_code', 'item_name',
  'quantity', 'color', 'customer_name', 'ship_by', 'brand',
  'email_subject', 'email_date', 'message_id', 'thread_id', 'item_index',
]

const SENSITIVE_PATTERN =
  /(email_body|body|pdf_text|raw|headers|authorization|token|secret|credential|admin|api_key|password|cookie)/i

const fmtDate = (d) => {
  if (!d) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const addDays = (n) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return d
}

const sanitizeRow = (row) => {
  if (!row || typeof row !== 'object') return {}
  return Object.fromEntries(
    Object.entries(row)
      .filter(([k]) => !SENSITIVE_PATTERN.test(k))
      .map(([k, v]) => [k, v == null ? '-' : String(v)])
  )
}

const getColumns = (rows) => {
  const keys = new Set(rows.flatMap(Object.keys))
  const known = PREVIEW_COLUMNS.filter((c) => keys.has(c))
  const extra = [...keys].filter((k) => !PREVIEW_COLUMNS.includes(k) && !SENSITIVE_PATTERN.test(k)).sort()
  return [...known, ...extra]
}

function SummaryTiles({ supplier }) {
  return (
    <div className="summary-grid">
      <div className="summary-tile"><span>{supplier.emails_found ?? 0}</span><p>Emails Found</p></div>
      <div className="summary-tile"><span>{supplier.orders_parsed ?? 0}</span><p>Orders Parsed</p></div>
      <div className="summary-tile"><span>{supplier.emails_skipped ?? 0}</span><p>Emails Skipped</p></div>
      <div className="summary-tile"><span>{supplier.duplicates_skipped ?? supplier.duplicates ?? 0}</span><p>Duplicates Skipped</p></div>
      <div className="summary-tile"><span>{supplier.rows_written ?? supplier.appended ?? 0}</span><p>Rows Written</p></div>
      <div className="summary-tile"><span>{supplier.would_append ?? 0}</span><p>Would Write</p></div>
    </div>
  )
}

function Diagnostics({ diagnostics = [] }) {
  const skipped = diagnostics.filter((d) => d.final_status !== 'parsed')
  if (!skipped.length) return null
  return (
    <div className="diagnostics-list">
      {skipped.map((d, i) => (
        <details key={`${d.message_id_short || 'msg'}-${i}`} className="diagnostic-item">
          <summary>
            <span>{d.subject || 'No subject'}</span>
            <strong>{d.safe_skip_reason || d.final_status}</strong>
          </summary>
          <dl>
            <div><dt>Message</dt><dd>{d.message_id_short || '-'}</dd></div>
            <div><dt>Parser</dt><dd>{d.parser_used || '-'}</dd></div>
            <div><dt>Body</dt><dd>{d.body_text_extracted ? `yes (${d.body_text_length})` : 'no'}</dd></div>
            <div><dt>HTML converted</dt><dd>{d.html_converted_to_text ? 'yes' : 'no'}</dd></div>
            <div><dt>Attachments</dt><dd>{d.attachment_count ?? 0}</dd></div>
            <div><dt>PDFs</dt><dd>{d.pdf_count ?? 0}</dd></div>
            <div><dt>PDF text</dt><dd>{d.pdf_text_extracted ? `yes (${d.pdf_text_length})` : 'no'}</dd></div>
            <div><dt>Missing</dt><dd>{(d.required_fields_missing || []).join(', ') || '-'}</dd></div>
          </dl>
          {(d.warnings || []).length > 0 && (
            <ul>
              {d.warnings.map((w, wi) => <li key={wi}>{w}</li>)}
            </ul>
          )}
        </details>
      ))}
    </div>
  )
}

export default function FetchOrders({ adminKey }) {
  const [allSuppliers, setAllSuppliers] = useState([])
  const [selectedId, setSelectedId] = useState('all-active')
  const [startDate, setStartDate] = useState(null)
  const [endDate, setEndDate] = useState(null)
  const [includeOrders, setIncludeOrders] = useState(true)
  const [maxRows, setMaxRows] = useState(10)
  const [batchResult, setBatchResult] = useState(null)
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchError, setBatchError] = useState(null)
  const [sandboxMsg, setSandboxMsg] = useState(null)
  const [sandboxLoading, setSandboxLoading] = useState(false)

  useEffect(() => {
    if (!adminKey) return
    fetch(`${API_URL}/suppliers`, { headers: { 'X-Admin-API-Key': adminKey } })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setAllSuppliers(d.suppliers || []))
      .catch(() => {})
  }, [adminKey])

  const activeSuppliers = allSuppliers.filter((s) => s.status === 'active' && s.email)

  const setQuickRange = (days) => {
    const end = new Date()
    const start = addDays(-days)
    setStartDate(start)
    setEndDate(end)
  }

  const getSupplierIds = () => {
    if (selectedId === 'all-active') return activeSuppliers.map((s) => s.id)
    return [selectedId]
  }

  const runBatch = async () => {
    if (!startDate || !endDate) { setBatchError('Select a date range first.'); return }
    if (!adminKey) { setBatchError('Enter admin key in the sidebar.'); return }
    const ids = getSupplierIds()
    if (!ids.length) { setBatchError('No active suppliers with email configured.'); return }

    setBatchLoading(true)
    setBatchError(null)
    setBatchResult(null)
    try {
      const r = await fetch(`${API_URL}/batch-orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-API-Key': adminKey },
        body: JSON.stringify({
          supplier_ids: ids,
          start_date: fmtDate(startDate),
          end_date: fmtDate(endDate),
          dry_run: true,
          include_orders: includeOrders,
          max_preview_rows: Math.min(Math.max(Number(maxRows) || 10, 1), MAX_PREVIEW_ROWS),
        }),
      })
      if (!r.ok) {
        const p = await r.json().catch(() => ({}))
        throw new Error(p?.detail?.message || p?.detail || `HTTP ${r.status}`)
      }
      setBatchResult(await r.json())
    } catch (e) {
      setBatchError(e.message)
    } finally {
      setBatchLoading(false)
    }
  }

  const runSandboxWrite = async () => {
    setSandboxLoading(true)
    setSandboxMsg(null)
    try {
      const r = await fetch(`${API_URL}/sandbox/write-dummy-order`, {
        method: 'POST',
        headers: { 'X-Admin-API-Key': adminKey },
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
      setSandboxMsg({ ok: true, text: `Sandbox write succeeded — ${data.rows_appended} row written to "${data.file_name}"` })
    } catch (e) {
      setSandboxMsg({ ok: false, text: e.message })
    } finally {
      setSandboxLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Fetch Orders</h1>
        <p>Dry-run only — no OneDrive writes from this UI.</p>
      </div>

      {!adminKey && <div className="error-msg">Enter your admin key in the sidebar.</div>}

      <div className="quick-btns">
        <button className="quick-btn" onClick={() => setQuickRange(1)} type="button">Last 24h</button>
        <button className="quick-btn" onClick={() => setQuickRange(7)} type="button">Last 7 days</button>
        <button className="quick-btn" onClick={() => setQuickRange(30)} type="button">Last 30 days</button>
        {(startDate || endDate) && (
          <button className="quick-btn" onClick={() => { setStartDate(null); setEndDate(null) }} type="button">
            Clear dates
          </button>
        )}
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Supplier</label>
          <select className="select-input" value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
            <option value="all-active">All Active Suppliers</option>
            {allSuppliers.map((s) => (
              <option key={s.id} value={s.id}>{s.name} ({s.id})</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Start Date</label>
          <DatePicker
            selected={startDate}
            onChange={setStartDate}
            selectsStart
            startDate={startDate}
            endDate={endDate}
            placeholderText="Start date"
            dateFormat="MM/dd/yyyy"
            isClearable
          />
        </div>

        <div className="form-group">
          <label>End Date</label>
          <DatePicker
            selected={endDate}
            onChange={setEndDate}
            selectsEnd
            startDate={startDate}
            endDate={endDate}
            minDate={startDate}
            placeholderText="End date"
            dateFormat="MM/dd/yyyy"
            isClearable
          />
        </div>

        <div className="form-group">
          <label>Preview rows</label>
          <input
            type="number"
            className="number-input"
            min={1}
            max={MAX_PREVIEW_ROWS}
            value={maxRows}
            onChange={(e) => setMaxRows(e.target.value)}
            style={{ width: 80 }}
          />
        </div>

        <div className="form-group" style={{ justifyContent: 'flex-end' }}>
          <label>&nbsp;</label>
          <label style={{ flexDirection: 'row', gap: 8, display: 'flex', alignItems: 'center', fontSize: 13, color: 'var(--muted)' }}>
            <input
              type="checkbox"
              checked={includeOrders}
              onChange={(e) => setIncludeOrders(e.target.checked)}
            />
            Include rows
          </label>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <button
          className="btn btn-primary"
          onClick={runBatch}
          disabled={batchLoading || !adminKey}
          type="button"
        >
          {batchLoading ? 'Running…' : 'Run Dry-Run Preview'}
        </button>

        <button
          className="btn btn-secondary"
          onClick={runSandboxWrite}
          disabled={sandboxLoading || !adminKey}
          type="button"
          title="Writes one dummy row to the sandbox OneDrive file only"
        >
          {sandboxLoading ? 'Writing…' : 'Write Dummy Sandbox Row'}
        </button>

        <button disabled className="btn btn-secondary" type="button" style={{ opacity: 0.4 }}>
          OneDrive Production Write — Disabled
        </button>
      </div>

      {batchError && <div className="error-msg">{batchError}</div>}

      {sandboxMsg && (
        <div className={`error-msg`} style={{
          color: sandboxMsg.ok ? 'var(--success)' : 'var(--danger)',
          background: sandboxMsg.ok ? 'rgba(62,207,142,0.08)' : undefined,
          borderColor: sandboxMsg.ok ? 'rgba(62,207,142,0.3)' : undefined,
        }}>
          {sandboxMsg.text}
        </div>
      )}

      {batchResult?.suppliers?.map((supplier) => {
        const safeRows = (supplier.orders || []).map(sanitizeRow)
        const cols = getColumns(safeRows)
        return (
          <div className="supplier-result" key={supplier.supplier_id}>
            <div className="supplier-result-header">
              <div>
                <h3>{supplier.supplier_name || supplier.supplier_id}</h3>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>{supplier.supplier_id}</span>
              </div>
              <span className="dry-run-pill">Dry-run only</span>
            </div>

            <SummaryTiles supplier={supplier} />
            <Diagnostics diagnostics={supplier.diagnostics || []} />

            {(supplier.errors || []).length > 0 && (
              <div className="error-list">
                {supplier.errors.map((msg, i) => <p key={i}>{msg}</p>)}
              </div>
            )}

            {includeOrders && safeRows.length > 0 && (
              <div className="table-wrap fetch-results-scroll" style={{ marginTop: 10 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      {cols.map((c) => <th key={c}>{c.replace(/_/g, ' ')}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {safeRows.map((row, i) => (
                      <tr key={i}>
                        <td style={{ color: 'var(--muted)', width: 32 }}>{i + 1}</td>
                        {cols.map((c) => <td key={c}>{row[c] || '-'}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
