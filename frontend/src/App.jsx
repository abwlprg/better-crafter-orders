import { useState, useRef } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const SUPPLIERS = [
  { id: 'stephen', name: 'Stephen', email: '7173783020@hellofax.com' }
]

function App() {
  const [selectedSupplier, setSelectedSupplier] = useState(SUPPLIERS[0].id)
  const [startDate, setStartDate] = useState(null)
  const [endDate, setEndDate] = useState(null)
  const [orders, setOrders] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  // Progress state
  const [progress, setProgress] = useState(null)
  const eventSourceRef = useRef(null)

  const safeErrorMessage = (message) => {
    if (!message) return 'Unable to preview orders'
    const lower = message.toLowerCase()
    if (lower.includes('admin api key') || lower.includes('protected')) {
      return 'Write actions are protected during stabilization and are not available from this UI.'
    }
    return message
  }

  const fetchOrders = async () => {
    setLoading(true)
    setError(null)
    setProgress({ percent: 0, message: '🚀 Starting...', step: 'init' })
    setOrders([])
    setStats(null)

    // Build query params from selected dates
    const params = new URLSearchParams()
    if (startDate) {
      const y = startDate.getFullYear()
      const m = String(startDate.getMonth() + 1).padStart(2, '0')
      const d = String(startDate.getDate()).padStart(2, '0')
      params.set('start_date', `${y}-${m}-${d}`)
    }
    if (endDate) {
      const y = endDate.getFullYear()
      const m = String(endDate.getMonth() + 1).padStart(2, '0')
      const d = String(endDate.getDate()).padStart(2, '0')
      params.set('end_date', `${y}-${m}-${d}`)
    }
    // If no dates selected → last 7 days (backend default)

    // Use SSE for streaming progress
    const query = params.toString()
    const evtSource = new EventSource(`${API_URL}/orders-stream${query ? `?${query}` : ''}`)
    eventSourceRef.current = evtSource

    evtSource.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data)
      setProgress(data)
    })

    evtSource.addEventListener('complete', (e) => {
      const data = JSON.parse(e.data)
      evtSource.close()
      eventSourceRef.current = null

      let filteredOrders = data.orders

      setOrders(filteredOrders)
      setStats({
        total: data.total_emails,
        parsed: data.parsed,
        failed: data.failed,
        pdfs: data.pdfs_found || 0,
        elapsed: data.elapsed || 0,
      })

      // Show completed progress briefly then clear
      setProgress({ percent: 100, message: data.message, step: 'done' })
      setTimeout(() => setProgress(null), 3000)
      setLoading(false)
    })

    evtSource.addEventListener('error', (e) => {
      // Check if it's a custom error event or connection error
      if (e.data) {
        const data = JSON.parse(e.data)
        setError(safeErrorMessage(data.message))
      } else {
        setError('Connection lost to server')
      }
      evtSource.close()
      eventSourceRef.current = null
      setProgress(null)
      setLoading(false)
    })

    evtSource.onerror = () => {
      // SSE connection error (not our custom error event)
      if (evtSource.readyState === EventSource.CLOSED) return
      evtSource.close()
      eventSourceRef.current = null
      if (!stats) {
        setError('Connection to server failed while previewing orders')
      }
      setProgress(null)
      setLoading(false)
    }
  }

  const clearDates = () => {
    setStartDate(null)
    setEndDate(null)
  }

  return (
    <div className="app">
      <header className="header">
        <h1>Order <span className="accent">Automation</span></h1>
        <p className="subtitle">Read-only Gmail order preview during stabilization</p>
      </header>

      <div className="filters">
        <div className="filter-group">
          <label>Supplier</label>
          <select 
            value={selectedSupplier} 
            onChange={(e) => setSelectedSupplier(e.target.value)}
            className="select-input"
          >
            {SUPPLIERS.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>From Date</label>
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
          <label>To Date</label>
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

        {(startDate || endDate) && (
          <div className="filter-group filter-action">
            <label>&nbsp;</label>
            <button onClick={clearDates} className="btn-clear">Clear dates</button>
          </div>
        )}
      </div>

      <div className="actions">
        <button onClick={fetchOrders} disabled={loading} className="btn btn-primary">
          {loading
            ? 'Previewing orders...'
            : startDate && endDate
              ? `Preview Orders ${startDate.toLocaleDateString('en-US', {month:'short', day:'numeric'})} - ${endDate.toLocaleDateString('en-US', {month:'short', day:'numeric'})}`
              : startDate
                ? `Preview Orders from ${startDate.toLocaleDateString('en-US', {month:'short', day:'numeric'})}`
                : 'Preview Orders (last 7 days)'}
        </button>

        {orders.length > 0 && (
          <button disabled className="btn btn-success">
            Write to OneDrive (admin-only)
          </button>
        )}
      </div>

      <p className="stabilization-note">
        OneDrive writing is protected and disabled from this UI during stabilization.
      </p>

      {error && <div className="error">{error}</div>}

      {/* Progress Bar */}
      {progress && (
        <div className="progress-container">
          <div className="progress-header">
            <span className="progress-message">{progress.message}</span>
            {progress.parsed !== undefined && (
              <span className="progress-stats">
                ✅ {progress.parsed} parsed • ❌ {progress.failed} skipped
                {progress.pdfs > 0 && ` • 📎 ${progress.pdfs} PDFs`}
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
              <span className="progress-count">{progress.current} / {progress.total} emails</span>
            )}
          </div>
        </div>
      )}

      {stats && (
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
              <span className="stat-label">📎 PDFs Found</span>
            </div>
          )}
          <div className="stat-card">
            <span className="stat-number">{stats.failed}</span>
            <span className="stat-label">Skipped</span>
          </div>

          {stats.elapsed > 0 && (
            <div className="stat-card">
              <span className="stat-number">{stats.elapsed}s</span>
              <span className="stat-label">⏱ Duration</span>
            </div>
          )}
        </div>
      )}

      {!stats && !loading && (
        <div className="empty-state">
          <p>Select a supplier, optionally set date filters, then preview orders from Gmail.</p>
        </div>
      )}

      {orders.length > 0 && (
        <div className="table-container">
          <h2>Orders ({orders.length})</h2>
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
              {orders.map((order, i) => (
                <tr key={i}>
                  <td className="row-num">{i + 1}</td>
                  <td>{order.order_date || '—'}</td>
                  <td className="mono">{order.item_code || '—'}</td>
                  <td>{order.item_name || '—'}</td>
                  <td className="center">{order.quantity || '—'}</td>
                  <td>{order.color || '—'}</td>
                  <td>{order.customer_name || '—'}</td>
                  <td>{order.ship_by || '—'}</td>
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
