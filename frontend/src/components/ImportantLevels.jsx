import { useState, useEffect } from 'react'
import { Copy, Check } from 'lucide-react'
import api from '../api'

const skip = k => k.includes('gex') || k.includes('gamma_wall')

function formatLine(data) {
  if (!data) return ''
  return Object.entries(data)
    .filter(([k]) => !skip(k))
    .map(([k, v]) => {
      const label = k.replace(/_/g, ' ')
      const val = typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v
      return `${label} ${val}`
    })
    .join(', ')
}

const toLabel = k => k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

function buildSierraChartString(nqLevels, qqqAsNq) {
  const parts = []
  if (nqLevels) {
    for (const [k, v] of Object.entries(nqLevels)) {
      if (!skip(k)) parts.push(`${toLabel(k)}, ${v}`)
    }
  }
  if (qqqAsNq) {
    for (const [k, v] of Object.entries(qqqAsNq)) {
      if (!skip(k)) parts.push(`${toLabel(k)} QQQ, ${v}`)
    }
  }
  return parts.join(', ')
}

function LevelLabel({ label, text }) {
  if (!text) return null
  return (
    <div className="lvl-row">
      <span className="lvl-label">{label}</span>
      <div className="lvl-val-wrap">
        <span className="lvl-val">{text}</span>
        <div className="lvl-tip">{text}</div>
      </div>
    </div>
  )
}

export default function ImportantLevels({ sessionDate, refreshKey }) {
  const [data, setData] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.get('/ingestion/session-levels', { params: { session_date: sessionDate } })
      .then(r => setData(r.data))
      .catch(() => {})
  }, [sessionDate, refreshKey])

  if (!data || (!data.nq_levels && !data.qqq_levels && !data.qqq_as_nq)) {
    return (
      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--c-dim)' }}>
        No levels data. Run ingestion after saving inputs.
      </span>
    )
  }

  const scString = buildSierraChartString(data.nq_levels, data.qqq_as_nq)

  const copyLevels = () => {
    if (!scString) return
    navigator.clipboard.writeText(scString).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="lvl-strip">
      <LevelLabel label="NQ" text={formatLine(data.nq_levels)} />
      <LevelLabel label="QQQ" text={formatLine(data.qqq_levels)} />
      <LevelLabel label="QQQ (NQ Eq)" text={formatLine(data.qqq_as_nq)} />
      {scString && (
        <button
          className={`lvl-copy${copied ? ' copied' : ''}`}
          onClick={copyLevels}
          title="Copy NQ + QQQ (NQ EQ) for Sierra Chart"
        >
          {copied ? <><Check size={11} /> Copied</> : <><Copy size={11} /> Copy Levels</>}
        </button>
      )}
    </div>
  )
}
