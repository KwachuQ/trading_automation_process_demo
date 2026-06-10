import { useState, useEffect } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { t, CardHeader } from './ui'
import api from '../api'

const SETUP_TYPES = ['MRS', 'MS', 'MRL', 'ML']

const SETUP_META = {
  MRS: { label: 'REVERSAL SHORT', dir: 'bear' },
  MS:  { label: 'MOMENTUM SHORT', dir: 'bear' },
  MRL: { label: 'REVERSAL LONG',  dir: 'bull' },
  ML:  { label: 'MOMENTUM LONG',  dir: 'bull' },
}

const EXAMPLE_SCENARIOS = [
  {
    setup_type: 'MRS',
    rationale: 'Price rejected from key resistance level with bearish divergence on 5m chart. Looking for a move down to the nearest support.',
    targets: 'TP1: 20500\nTP2: 20450\nSL: 20600'
  },
  {
    setup_type: 'ML',
    rationale: 'Breakout above the pre-market high with strong volume. Expecting continuation towards the next daily liquidity pool.',
    targets: 'TP1: 20750\nTP2: 20800\nSL: 20650'
  },
  {
    setup_type: 'MRL',
    rationale: 'Sweep of the overnight low, followed by a strong bullish structure shift. Good R:R for a bounce play.',
    targets: 'TP1: 20400\nTP2: 20500\nSL: 20300'
  },
  {
    setup_type: 'MS',
    rationale: 'Breakdown of the Asian session consolidation box. Momentum is clearly downwards. Riding the trend.',
    targets: 'TP1: 20200\nTP2: 20100\nSL: 20350'
  }
]

function parseTargets(raw) {
  if (!raw) return []
  return raw
    .split(/[,\n]+/)
    .map(s => s.trim())
    .filter(Boolean)
}

function ScenarioCard({ scenario, index, selected, onSelect, onDelete }) {
  const meta = SETUP_META[scenario.setup_type] ?? { label: scenario.setup_type, dir: 'bull' }
  const chips = parseTargets(scenario.targets)

  return (
    <div
      className={`sc-card sc-card--${meta.dir}${selected ? ' sc-card--selected' : ''}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onSelect()}
    >
      <div className="sc-card-hdr">
        <span className="sc-index">#{index + 1}</span>
        <span className={`sc-badge sc-badge--${meta.dir}`}>{meta.label}</span>
        <button
          className="scenario-icon-btn scenario-icon-btn--danger sc-delete"
          onClick={e => { e.stopPropagation(); onDelete() }}
          title="Delete scenario"
        >
          <Trash2 size={12} />
        </button>
      </div>
      <p className="sc-rationale">{scenario.rationale || <span style={{ color: t.dim }}>No thesis yet</span>}</p>
      {chips.length > 0 && (
        <div className="sc-chips">
          {chips.map((chip, i) => (
            <span key={i} className="sc-chip">{chip}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function ScenarioEditor({ scenario, index, saving, onSave, onDiscard }) {
  const [setupType, setSetupType] = useState(scenario?.setup_type ?? 'MRS')
  const [rationale, setRationale] = useState(scenario?.rationale ?? '')
  const [targets, setTargets] = useState(scenario?.targets ?? '')

  // Sync when external scenario changes (e.g. switching selection)
  useEffect(() => {
    setSetupType(scenario?.setup_type ?? 'MRS')
    setRationale(scenario?.rationale ?? '')
    setTargets(scenario?.targets ?? '')
  }, [scenario])

  const dir = SETUP_META[setupType]?.dir ?? 'bull'
  const isDirty = scenario
    ? (setupType !== scenario.setup_type || rationale !== scenario.rationale || targets !== scenario.targets)
    : (rationale.trim() !== '' || targets.trim() !== '')

  function handleSave() {
    onSave({ setup_type: setupType, rationale: rationale.trim(), targets: targets.trim() })
  }

  return (
    <div className={`sc-editor sc-editor--${dir}${saving ? ' sc-editor--saving' : ''}`}>
      {/* Setup type selector */}
      <div className="sc-editor-hdr">
        <span className="sc-editor-idx">#{index + 1}</span>
        <div className="sc-setup-ctrl">
          {SETUP_TYPES.map(st => {
            const d = SETUP_META[st].dir
            return (
              <button
                key={st}
                type="button"
                className={`sc-setup-opt sc-setup-opt--${d}${setupType === st ? ' active' : ''}`}
                onClick={() => setSetupType(st)}
              >
                {st}
              </button>
            )
          })}
        </div>
      </div>

      {/* Thesis */}
      <div className="sc-field">
        <label className="sc-field-label">Thesis</label>
        <textarea
          className="sc-textarea sc-textarea--thesis input-field"
          rows={7}
          value={rationale}
          onChange={e => setRationale(e.target.value)}
          placeholder="Why this setup? Key confluences, context, invalidation level..."
        />
        <span className="sc-charcount">{rationale.length} chars</span>
      </div>

      {/* Targets */}
      <div className="sc-field">
        <label className="sc-field-label">Targets</label>
        <textarea
          className="sc-textarea sc-textarea--targets input-field"
          rows={3}
          value={targets}
          onChange={e => setTargets(e.target.value)}
          placeholder="TP1: 20500, TP2: 20620, SL: 20380"
        />
      </div>

      {/* Footer actions */}
      <div className="sc-editor-footer">
        <button
          className={`sc-save-btn sc-save-btn--${dir}${isDirty ? ' dirty' : ''}`}
          onClick={handleSave}
          disabled={saving || !rationale.trim() || !targets.trim()}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button className="sc-cancel-btn" onClick={onDiscard}>
          {scenario ? 'Cancel' : 'Discard'}
        </button>
      </div>
    </div>
  )
}

export default function Scenarios({ sessionDate }) {
  const [scenarios, setScenarios] = useState([])
  const [selectedIdx, setSelectedIdx] = useState(null)
  const [adding, setAdding] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get(`/session/scenarios/${sessionDate}`)
      .then(r => setScenarios(r.data.map(s => ({
        setup_type: s.setup_type,
        rationale: s.rationale,
        targets: s.targets,
      }))))
      .catch(() => {})
  }, [sessionDate])

  async function persistAll(updated) {
    setSaving(true)
    try {
      const payload = {
        session_date: sessionDate,
        scenarios: updated.map((s, i) => ({
          scenario_number: i + 1,
          setup_type: s.setup_type,
          rationale: s.rationale,
          targets: s.targets,
        })),
      }
      const r = await api.post('/session/scenarios', payload)
      setScenarios(r.data.map(s => ({
        setup_type: s.setup_type,
        rationale: s.rationale,
        targets: s.targets,
      })))
    } catch (err) {
      console.error('Failed to save scenarios:', err)
    } finally {
      setSaving(false)
    }
  }

  function handleSaveEdit(data) {
    const updated = [...scenarios]
    updated[selectedIdx] = data
    setSelectedIdx(null)
    persistAll(updated)
  }

  function handleSaveNew(data) {
    const updated = [...scenarios, data]
    setAdding(false)
    persistAll(updated)
  }

  function handleDelete(idx) {
    const updated = scenarios.filter((_, i) => i !== idx)
    if (selectedIdx === idx) setSelectedIdx(null)
    persistAll(updated)
  }

  function handleDiscard() {
    if (adding) setAdding(false)
    else setSelectedIdx(null)
  }

  const editorScenario = adding ? null : selectedIdx !== null ? scenarios[selectedIdx] : null
  const editorIdx = adding ? scenarios.length : selectedIdx
  const editorActive = adding || selectedIdx !== null

  return (
    <div className="sc-workspace">
      {/* Editor panel */}
      <div className="sc-editor-panel">
        {editorActive ? (
          <ScenarioEditor
            key={adding ? 'new' : selectedIdx}
            scenario={editorScenario}
            index={editorIdx}
            saving={saving}
            onSave={adding ? handleSaveNew : handleSaveEdit}
            onDiscard={handleDiscard}
          />
        ) : (
          <div className="sc-editor-idle">
            {scenarios.length > 0
              ? 'Select a scenario to edit'
              : 'Add a scenario to get started'}
          </div>
        )}
      </div>

      {/* List panel */}
      <div className="sc-list-panel">
        <div className="sc-list-hdr">
          <CardHeader eyebrow="Scenarios" badge={scenarios.length > 0 ? 'complete' : 'pending'} />
        </div>
        <div className="sc-list">
          {scenarios.length === 0 && !adding && (
            <div className="sc-list-empty">No scenarios yet</div>
          )}
          {scenarios.map((s, i) => (
            <ScenarioCard
              key={i}
              scenario={s}
              index={i}
              selected={!adding && selectedIdx === i}
              onSelect={() => { setAdding(false); setSelectedIdx(i) }}
              onDelete={() => handleDelete(i)}
            />
          ))}
        </div>
        <div style={{ display: 'flex', gap: '8px', padding: '0 10px 10px' }}>
          <button
            className="sc-add-btn"
            onClick={() => { setSelectedIdx(null); setAdding(true) }}
            disabled={saving || adding}
            style={{ flex: 1, margin: 0 }}
          >
            <Plus size={13} />
            Add Scenario
          </button>
          {scenarios.length === 0 && (
            <button
              className="sc-add-btn"
              onClick={() => persistAll(EXAMPLE_SCENARIOS)}
              disabled={saving}
              style={{ flex: 1, margin: 0, background: 'rgba(255, 255, 255, 0.05)' }}
            >
              Load Examples
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
