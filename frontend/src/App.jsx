import { useRef, useState } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import './App.css'

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/$/, '')
const MAX_PREVIEW_ROWS = 100

const SUPPLIERS = [
  { id: 'stephen', name: 'Stephen' },
  { id: 'steven', name: 'Steven' },
]

const PREVIEW_COLUMNS = [
  'supplier_id',
  'supplier_name',
  'order_date',
  'item_code',
  'item_name',
  'quantity',
  'color',
  'customer_name',
  'ship_by',
  'brand',
  'email_subject',
  'email_date',
  'message_id',
  'thread_id',
  'item_index',
]

const SENSITIVE_FIELD_PATTERN =
  /(email_body|body|pdf_text|raw|headers|authorization|token|secret|credential|admin|api_key|password|cookie)/i

const formatDateForApi = (date) => {
  if (!date) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const toDisplayLabel = (key) =>
  key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())

const clampPreviewRows = (value) => {
  const parsed = Number.parseInt(value, 10)
  if (Number.isNaN(parsed)) return 10
  return Math.min(Math.max(parsed, 1), MAX_PREVIEW_ROWS)
}

const safeCellValue = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return '[omitted]'
}

const sanitizePreviewRow = (row) => {
  if (!row || typeof row !== 'object' || Array.isArray(row)) return {}

  return Object.entries(row).reduce((safeRow, [key, value]) => {
    if (SENSITIVE_FIELD_PATTERN.test(key)) return safeRow
    return {
      ...safeRow,
      [key]: safeCellValue(value),
    }
  }, {})
}

const getPreviewColumns = (rows) => {
  const keys = new Set(rows.flatMap((row) => Object.keys(row)))
  const knownColumns = PREVIEW_COLUMNS.filter((column) => keys.has(column))
  const extraColumns = [...keys]
    .filter((key) => !PREVIEW_COLUMNS.includes(key))
    .filter((key) => !SENSITIVE_FIELD_PATTERN.test(key))
    .sort()

  return [...knownColumns, ...extraColumns]
}

const getApiErrorMessage = async (response) => {
  try {
    const payload = await response.json()
    if (typeof payload?.detail === 'string') return payload.detail
    if (typeof payload?.detail?.message === 'string') return payload.detail.message
    if (typeof payload?.message === 'string') return payload.message
  } catch {
    // Keep error handling local without exposing response payloads in logs.
  }
  return `Request failed with status ${response.status}`
}

function BatchDryRunResult({ result, includeOrders }) {
  if (!result?.suppliers?.length) return null

  return (
    <section className="result-panel" aria-labelledby="batch-result-heading">
      <div className="section-heading">
        <p className="eyebrow">Batch Dry-Run Preview</p>
        <h2 id="batch-result-heading">Dry-run summary</h2>
      </div>

      <div className="supplier-results">
        {result.suppliers.map((supplier) => {
          const safeRows = (supplier.orders || []).map(sanitizePreviewRow)
          const previewColumns = getPreviewColumns(safeRows)
          const errors = supplier.errors || []

          return (
            <article className="supplier-result" key={supplier.supplier_id}>
              <div className="supplier-result-header">
                <div>
                  <h3>{supplier.supplier_name || supplier.supplier_id}</h3>
                  <p className="muted">Supplier ID: {supplier.supplier_id}</p>
                </div>
                <span className="dry-run-pill">Dry-run only</span>
              </div>

              <div className="summary-grid">
                <div className="summary-tile">
                  <span>{supplier.emails_found ?? 0}</span>
                  <p>Emails Found</p>
                </div>
                <div className="summary-tile">
                  <span>{supplier.orders_parsed ?? 0}</span>
                  <p>Orders Parsed</p>
                </div>
                <div className="summary-tile">
                  <span>{supplier.invalid_rows ?? 0}</span>
                  <p>Invalid Rows</p>
                </div>
                <div className="summary-tile">
                  <span>{supplier.would_append ?? 0}</span>
                  <p>Would Append</p>
                </div>
                <div className="summary-tile">
                  <span>{supplier.appended ?? 0}</span>
                  <p>Appended</p>
                </div>
                <div className="summary-tile">
                  <span>{errors.length}</span>
                  <p>Errors</p>
                </div>
              </div>

              {errors.length > 0 && (
                <div className="error-list">
                  {errors.map((message, index) => (
                    <p key={`${supplier.supplier_id}-error-${index}`}>{message}</p>
                  ))}
                </div>
              )}

              {includeOrders && safeRows.length > 0 && previewColumns.length > 0 && (
                <div className="table-container preview-table-container">
                  <h3>Sanitized Preview Rows ({safeRows.length})</h3>
                  <table className="orders-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        {previewColumns.map((column) => (
                          <th key={column}>{toDisplayLabel(column)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {safeRows.map((row, rowIndex) => (
                        <tr key={`${supplier.supplier_id}-preview-${rowIndex}`}>
                          <td className="row-num">{rowIndex + 1}</td>
                          {previewColumns.map((column) => (
                            <td key={column}>{row[column] || '-'}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {includeOrders && safeRows.length === 0 && (
                <p className="muted preview-empty">No sanitized preview rows were returned.</p>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}

function App() {
  const [selectedSupplier, setSelectedSupplier] = useState(SUPPLIERS[0].id)
  const [startDate, setStartDate] = useState(null)
  const [endDate, setEndDate] = useState(null)
  const [adminKey, setAdminKey] = useState('')
  const [includeOrders, setIncludeOrders] = useState(true)
  const [maxPreviewRows, setMaxPreviewRows] = useState(10)
  const [batchResult, setBatchResult] = useState(null)
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchError, setBatchError] = useState(null)

  const [orders, setOrders] = useState([])
  const [stats, setStats] = useState(null)
  const [streamLoading, setStreamLoading] = useState(false)
  const [streamError, setStreamError] = useState(null)

  const [progress, setProgress] = useState(null)
  const eventSourceRef = useRef(null)

  const safeErrorMessage = (message, previewType = 'streaming') => {
    if (!message) return 'Unable to preview orders'
    const lower = message.toLowerCase()
    if (lower.includes('admin api key') || lower.includes('protected')) {
      if (previewType === 'batch') {
        return 'Dry-run preview is admin-protected. Check the local admin key and try again.'
      }
      return 'Write actions are protected during stabilization and are not available from this UI.'
    }
    return message
  }

  const validateBatchPreview = () => {
    if (!selectedSupplier) return 'Choose a supplier before running the dry-run preview.'
    if (!startDate) return 'Choose a start date for the dry-run preview.'
    if (!endDate) return 'Choose an end date for the dry-run preview.'
    if (startDate > endDate) return 'Start date must be on or before end date.'
    if (!adminKey.trim()) return 'Enter a local admin key to run the dry-run preview.'

    const parsedPreviewRows = Number.parseInt(maxPreviewRows, 10)
    if (
      Number.isNaN(parsedPreviewRows) ||
      parsedPreviewRows < 1 ||
      parsedPreviewRows > MAX_PREVIEW_ROWS
    ) {
      return `Preview rows must be between 1 and ${MAX_PREVIEW_ROWS}.`
    }

    return null
  }

  const runBatchDryRunPreview = async () => {
    const validationError = validateBatchPreview()
    if (validationError) {
      setBatchError(validationError)
      return
    }

    const previewRowCap = clampPreviewRows(maxPreviewRows)
    setMaxPreviewRows(previewRowCap)
    setBatchLoading(true)
    setBatchError(null)
    setBatchResult(null)

    try {
      const response = await fetch(`${API_URL}/batch-orders`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-API-Key': adminKey.trim(),
        },
        body: JSON.stringify({
          supplier_ids: [selectedSupplier],
          start_date: formatDateForApi(startDate),
          end_date: formatDateForApi(endDate),
          dry_run: true,
          include_orders: includeOrders,
          max_preview_rows: previewRowCap,
        }),
      })

      if (!response.ok) {
        throw new Error(await getApiErrorMessage(response))
      }

      const data = await response.json()
      setBatchResult(data)
    } catch (requestError) {
      setBatchError(safeErrorMessage(requestError.message, 'batch'))
    } finally {
      setBatchLoading(false)
    }
  }

  const fetchOrders = async () => {
    setStreamLoading(true)
    setStreamError(null)
    setProgress({ percent: 0, message: 'Starting streaming preview...', step: 'init' })
    setOrders([])
    setStats(null)

    const params = new URLSearchParams()
    const formattedStartDate = formatDateForApi(startDate)
    const formattedEndDate = formatDateForApi(endDate)

    if (formattedStartDate) params.set('start_date', formattedStartDate)
    if (formattedEndDate) params.set('end_date', formattedEndDate)

    const query = params.toString()
    const evtSource = new EventSource(`${API_URL}/orders-stream${query ? `?${query}` : ''}`)
    eventSourceRef.current = evtSource

    evtSource.addEventListener('progress', (event) => {
      const data = JSON.parse(event.data)
      setProgress(data)
    })

    evtSource.addEventListener('complete', (event) => {
      const data = JSON.parse(event.data)
      evtSource.close()
      eventSourceRef.current = null

      setOrders(data.orders || [])
      setStats({
        total: data.total_emails,
        parsed: data.parsed,
        failed: data.failed,
        pdfs: data.pdfs_found || 0,
        elapsed: data.elapsed || 0,
      })

      setProgress({ percent: 100, message: data.message, step: 'done' })
      setTimeout(() => setProgress(null), 3000)
      setStreamLoading(false)
    })

    evtSource.addEventListener('error', (event) => {
      if (event.data) {
        const data = JSON.parse(event.data)
        setStreamError(safeErrorMessage(data.message))
      } else {
        setStreamError('Connection lost to server')
      }
      evtSource.close()
      eventSourceRef.current = null
      setProgress(null)
      setStreamLoading(false)
    })

    evtSource.onerror = () => {
      if (evtSource.readyState === EventSource.CLOSED) return
      evtSource.close()
      eventSourceRef.current = null
      setStreamError('Connection to server failed while previewing orders')
      setProgress(null)
      setStreamLoading(false)
    }
  }

  const clearDates = () => {
    setStartDate(null)
    setEndDate(null)
  }

  const displayDateRange =
    startDate && endDate
      ? `${startDate.toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
        })} - ${endDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
      : null

  return (
    <div className="app">
      <header className="header">
        <h1>
          Order <span className="accent">Automation</span>
        </h1>
        <p className="subtitle">Read-only order previews during stabilization</p>
      </header>

      <section className="control-panel" aria-labelledby="batch-preview-heading">
        <div className="section-heading">
          <p className="eyebrow">Batch Dry-Run Preview</p>
          <h2 id="batch-preview-heading">Preview supplier batch results</h2>
        </div>

        <div className="filters">
          <div className="filter-group">
            <label htmlFor="supplier">Supplier</label>
            <select
              id="supplier"
              value={selectedSupplier}
              onChange={(event) => setSelectedSupplier(event.target.value)}
              className="select-input"
            >
              {SUPPLIERS.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group">
            <label>Start Date</label>
            <DatePicker
              selected={startDate}
              onChange={(date) => setStartDate(date)}
              selectsStart
              startDate={startDate}
              endDate={endDate}
              placeholderText="Select start"
              className="date-input"
              dateFormat="MM/dd/yyyy"
              isClearable
              calendarClassName="dark-calendar"
            />
          </div>

          <div className="filter-group">
            <label>End Date</label>
            <DatePicker
              selected={endDate}
              onChange={(date) => setEndDate(date)}
              selectsEnd
              startDate={startDate}
              endDate={endDate}
              minDate={startDate}
              placeholderText="Select end"
              className="date-input"
              dateFormat="MM/dd/yyyy"
              isClearable
              calendarClassName="dark-calendar"
            />
          </div>

          <div className="filter-group admin-key-group">
            <label htmlFor="admin-key">Local admin key for dry-run preview</label>
            <input
              id="admin-key"
              type="password"
              value={adminKey}
              onChange={(event) => setAdminKey(event.target.value)}
              className="text-input"
              autoComplete="off"
              spellCheck="false"
            />
            <p className="field-note">
              This key is used only in memory for the local dry-run request. It is not saved.
            </p>
          </div>

          <div className="filter-group compact-control">
            <label htmlFor="max-preview-rows">Preview Row Cap</label>
            <input
              id="max-preview-rows"
              type="number"
              min="1"
              max={MAX_PREVIEW_ROWS}
              value={maxPreviewRows}
              onChange={(event) => setMaxPreviewRows(event.target.value)}
              onBlur={() => setMaxPreviewRows(clampPreviewRows(maxPreviewRows))}
              className="number-input"
            />
          </div>

          <div className="filter-group checkbox-control">
            <label htmlFor="include-orders">Preview Rows</label>
            <label className="checkbox-row">
              <input
                id="include-orders"
                type="checkbox"
                checked={includeOrders}
                onChange={(event) => setIncludeOrders(event.target.checked)}
              />
              Include sanitized rows
            </label>
          </div>

          {(startDate || endDate) && (
            <div className="filter-group filter-action">
              <label>&nbsp;</label>
              <button onClick={clearDates} className="btn-clear" type="button">
                Clear dates
              </button>
            </div>
          )}
        </div>

        <div className="actions">
          <button
            onClick={runBatchDryRunPreview}
            disabled={batchLoading || streamLoading}
            className="btn btn-primary"
            type="button"
          >
            {batchLoading
              ? 'Running dry-run preview...'
              : displayDateRange
                ? `Run Batch Dry-Run Preview ${displayDateRange}`
                : 'Run Batch Dry-Run Preview'}
          </button>

          <button
            onClick={fetchOrders}
            disabled={batchLoading || streamLoading}
            className="btn btn-secondary"
            type="button"
          >
            {streamLoading ? 'Streaming preview...' : 'Run Streaming Preview'}
          </button>

          <button disabled className="btn btn-success" type="button">
            OneDrive Write Disabled
          </button>
        </div>

        <p className="stabilization-note">
          Dry-run mode is always on for the batch preview. No OneDrive write happens from this
          UI flow.
        </p>
      </section>

      {batchError && <div className="error">{batchError}</div>}
      {streamError && <div className="error">{streamError}</div>}

      {progress && (
        <div className="progress-container">
          <div className="progress-header">
            <span className="progress-message">{progress.message}</span>
            {progress.parsed !== undefined && (
              <span className="progress-stats">
                {progress.parsed} parsed / {progress.failed} skipped
                {progress.pdfs > 0 && ` / ${progress.pdfs} PDFs`}
              </span>
            )}
          </div>
          <div className="progress-bar-track">
            <div
              className={`progress-bar-fill ${progress.percent === 100 ? 'complete' : ''}`}
              style={{ width: `${progress.percent}%` }}
            />
          </div>
          <div className="progress-footer">
            <span className="progress-percent">{progress.percent}%</span>
            {progress.current && progress.total && (
              <span className="progress-count">
                {progress.current} / {progress.total} emails
              </span>
            )}
          </div>
        </div>
      )}

      <BatchDryRunResult result={batchResult} includeOrders={includeOrders} />

      {stats && (
        <section className="streaming-results" aria-labelledby="streaming-result-heading">
          <div className="section-heading">
            <p className="eyebrow">Streaming Preview</p>
            <h2 id="streaming-result-heading">Read-only Gmail preview</h2>
          </div>

          <div className="stats">
            <div className="stat-card">
              <span className="stat-number">{stats.total}</span>
              <span className="stat-label">Emails Found</span>
            </div>
            <div className="stat-card">
              <span className="stat-number">{stats.parsed}</span>
              <span className="stat-label">Orders Parsed</span>
            </div>
            {stats.pdfs > 0 && (
              <div className="stat-card">
                <span className="stat-number">{stats.pdfs}</span>
                <span className="stat-label">PDFs Found</span>
              </div>
            )}
            <div className="stat-card">
              <span className="stat-number">{stats.failed}</span>
              <span className="stat-label">Skipped</span>
            </div>

            {stats.elapsed > 0 && (
              <div className="stat-card">
                <span className="stat-number">{stats.elapsed}s</span>
                <span className="stat-label">Duration</span>
              </div>
            )}
          </div>
        </section>
      )}

      {!stats && !batchResult && !streamLoading && !batchLoading && (
        <div className="empty-state">
          <p>Select a supplier and date range, then run a dry-run preview.</p>
        </div>
      )}

      {orders.length > 0 && (
        <div className="table-container">
          <h2>Streaming Preview Orders ({orders.length})</h2>
          <table className="orders-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Date</th>
                <th>Item No.</th>
                <th>Item Name</th>
                <th>QTY</th>
                <th>Color</th>
                <th>Customer</th>
                <th>Ship By</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order, index) => (
                <tr key={`${order.message_id || 'stream'}-${index}`}>
                  <td className="row-num">{index + 1}</td>
                  <td>{order.order_date || '-'}</td>
                  <td className="mono">{order.item_code || '-'}</td>
                  <td>{order.item_name || '-'}</td>
                  <td className="center">{order.quantity || '-'}</td>
                  <td>{order.color || '-'}</td>
                  <td>{order.customer_name || '-'}</td>
                  <td>{order.ship_by || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default App
