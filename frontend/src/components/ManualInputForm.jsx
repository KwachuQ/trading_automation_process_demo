import { useState } from 'react'
import { t, InlineMsg, Btn, SegmentControl } from './ui'
import api from '../api'

function StatusLine({ status, label }) {
  if (!status) return null
  const ok = status[label] === 'ok'
  return (
    <p style={{ marginTop: 4, fontSize: 11, fontFamily: t.mono, fontWeight: 600, color: ok ? t.success : t.error }}>
      {ok ? 'Saved' : 'Failed to save'}
    </p>
  )
}

export default function ManualInputForm({ onComplete }) {
  const [combinedString, setCombinedString] = useState(
    "$NQ1!: Call Resistance, 26000, Put Support, 24000, HVL, 24740, 1D Min, 26049.27, 1D Max, 26681.73, Call Resistance 0DTE, 26050, Put Support 0DTE, 25970, HVL 0DTE, 25230\n\n$QQQ: Call Resistance, 640, Put Support, 590, HVL, 609.78, 1D Min, 629.72, 1D Max, 645.08, Call Resistance 0DTE, 640, Put Support 0DTE, 626, HVL 0DTE, 626"
  )
  const [gammaNq, setGammaNq] = useState('positive')
  const [gammaQqq, setGammaQqq] = useState('positive')
  const [expMoveMaxPctNq, setExpMoveMaxPctNq] = useState('1.57')
  const [expMoveMaxPctQqq, setExpMoveMaxPctQqq] = useState('1.60')
  const [loading, setLoading] = useState(false)
  const [sectionStatus, setSectionStatus] = useState(null)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setSectionStatus(null)

    const statuses = {}

    try {
      await api.post('/ingestion/manual-string', {
        combined_string: combinedString.trim(),
      })
      statuses['Levels'] = 'ok'
    } catch (err) {
      const detail = err?.response?.data?.detail ?? 'Parse error'
      statuses['Levels'] = 'error'
      setError(detail)
    }

    try {
      const gammaNqData = { regime: gammaNq }
      if (expMoveMaxPctNq !== '') gammaNqData.exp_move_max_pct = parseFloat(expMoveMaxPctNq)
      await api.post('/ingestion/manual', { input_type: 'gamma_nq', data: gammaNqData })
      statuses['Gamma NQ'] = 'ok'
    } catch {
      statuses['Gamma NQ'] = 'error'
    }

    try {
      const gammaQqqData = { regime: gammaQqq }
      if (expMoveMaxPctQqq !== '') gammaQqqData.exp_move_max_pct = parseFloat(expMoveMaxPctQqq)
      await api.post('/ingestion/manual', { input_type: 'gamma_qqq', data: gammaQqqData })
      statuses['Gamma QQQ'] = 'ok'
    } catch {
      statuses['Gamma QQQ'] = 'error'
    }

    setLoading(false)
    setSectionStatus(statuses)

    const allOk = Object.values(statuses).every(s => s === 'ok')
    if (allOk && onComplete) onComplete()
  }

  const inputStyle = {
    width: '100%',
    background: t.inputBg,
    border: `1px solid ${t.border}`,
    borderRadius: 4,
    padding: '6px 8px',
    fontSize: 12,
    fontFamily: t.mono,
    color: t.text,
    outline: 'none',
    boxSizing: 'border-box',
  }

  const labelStyle = {
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: t.muted,
    fontFamily: t.mono,
  }

  const subLabelStyle = {
    fontSize: 11,
    color: t.dim,
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <InlineMsg type="error" message={error} onDismiss={() => setError(null)} />

      {/* MenthorQ Levels */}
      <div>
        <div style={{ ...labelStyle, marginBottom: 6 }}>MenthorQ Levels (NQ + QQQ)</div>
        <textarea
          required
          rows={3}
          value={combinedString}
          onChange={e => setCombinedString(e.target.value)}
          placeholder="Call Resistance, 26000, Put Support, 24000, HVL, 24740, ..."
          style={{ ...inputStyle, resize: 'vertical' }}
          className="input-field"
        />
        <StatusLine status={sectionStatus} label="Levels" />
      </div>

      {/* NQ Gamma */}
      <div style={{ borderTop: `1px solid ${t.border}`, paddingTop: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={labelStyle}>NQ Gamma</span>
          <SegmentControl value={gammaNq} onChange={setGammaNq} options={['positive', 'negative']} />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={subLabelStyle}>Exp Move Max %</span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={expMoveMaxPctNq}
            onChange={e => setExpMoveMaxPctNq(e.target.value)}
            placeholder="1.25"
            className="input-field"
            style={{ ...inputStyle, width: 80 }}
          />
        </label>
        <StatusLine status={sectionStatus} label="Gamma NQ" />
      </div>

      {/* QQQ Gamma */}
      <div style={{ borderTop: `1px solid ${t.border}`, paddingTop: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={labelStyle}>QQQ Gamma</span>
          <SegmentControl value={gammaQqq} onChange={setGammaQqq} options={['positive', 'negative']} />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={subLabelStyle}>Exp Move Max %</span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={expMoveMaxPctQqq}
            onChange={e => setExpMoveMaxPctQqq(e.target.value)}
            placeholder="1.25"
            className="input-field"
            style={{ ...inputStyle, width: 80 }}
          />
        </label>
        <StatusLine status={sectionStatus} label="Gamma QQQ" />
      </div>

      <Btn type="submit" disabled={loading} loading={loading} style={{ width: '100%' }}>
        {loading ? 'Saving' : 'Save Inputs'}
      </Btn>
    </form>
  )
}
