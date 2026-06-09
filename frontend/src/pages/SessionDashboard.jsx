import React, { useState, useEffect } from 'react';
import { useLiveSession } from '../hooks/useLiveSession';
import { CardHeader } from '../components/ui';

// ---------------------------------------------------------------------------
// ScoreBand — returns a CSS class and label based on the numeric score.
// ---------------------------------------------------------------------------
function getScoreBand(score) {
  if (score <= 20) return { cls: 'sd-score-no-trade',  label: '0–20 · No Trade' };
  if (score <= 40) return { cls: 'sd-score-weak',      label: '21–40 · Weak' };
  if (score <= 60) return { cls: 'sd-score-selective', label: '41–60 · Selective' };
  if (score <= 80) return { cls: 'sd-score-favorable', label: '61–80 · Favorable' };
  return              { cls: 'sd-score-strong',    label: '81–100 · Strong' };
}

// ---------------------------------------------------------------------------
// SetupScoreCard — compact card for a single pre-market setup score.
// Props:
//   setup         — the setup object from the live session response
//   isActive      — boolean, true when this card is the marked active setup
//   onMarkActive  — callback(setup_type) invoked when the toggle is clicked
// ---------------------------------------------------------------------------
function SetupScoreCard({ setup, isActive, onMarkActive }) {
  const [expanded, setExpanded] = useState(false);

  const isLong = setup.setup_type?.endsWith('L');
  const badgeCls = isLong ? 'sd-setup-badge--long' : 'sd-setup-badge--short';
  const { cls: bandCls, label: bandLabel } = getScoreBand(setup.score || 0);

  // Toggle: clicking an already-active card deactivates it.
  const handleToggle = () => {
    onMarkActive(isActive ? '' : setup.setup_type);
  };

  return (
    <div className={`sd-setup-card${isActive ? ' sd-setup-card--active' : ''}`}>
      {/* Header row: badge + scenario ref on the left, score on the right */}
      <div className="sd-setup-card-hdr">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={badgeCls}>{setup.setup_type}</span>
          <span className="sd-setup-scenario-num">Scenario #{setup.scenario_number}</span>
        </div>
        <div className="sd-setup-score-group">
          <span className="sd-setup-score">{setup.score?.toFixed(1) ?? '0'}</span>
          <span className={bandCls} style={{ fontSize: 12.1 }}>{bandLabel}</span>
        </div>
      </div>

      {/* Rationale excerpt */}
      {setup.rationale && (
        <div className="sd-setup-rationale">
          &ldquo;{setup.rationale}&rdquo;
        </div>
      )}

      {/* Active toggle pill */}
      <button
        id={`sd-active-toggle-${setup.setup_type}`}
        className={`sd-active-toggle${isActive ? ' sd-active-toggle--on' : ''}`}
        onClick={handleToggle}
        title={isActive ? 'Deactivate this setup' : 'Mark as active for this session'}
      >
        {isActive ? (
          <>
            <span className="sd-active-dot" />
            Active
          </>
        ) : (
          'Mark as Active'
        )}
      </button>

      {/* Criteria breakdown — collapsible */}
      <div>
        <button
          className="sd-breakdown-toggle"
          onClick={() => setExpanded(v => !v)}
        >
          {expanded ? 'Hide breakdown ↑' : 'Show breakdown ↓'}
        </button>
        {expanded && (
          <div className="sd-breakdown-list" style={{ marginTop: 8 }}>
            {setup.breakdown?.map((item, i) => (
              <div key={i} className="sd-breakdown-row">
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1 }}>
                  <span style={{ color: item.matched ? 'var(--c-bull)' : 'var(--c-dim)', flexShrink: 0 }}>
                    {item.matched ? '✓' : '✗'}
                  </span>
                  <span style={{ color: 'var(--c-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.criterion_name}
                  </span>
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-dim)', minWidth: 40, textAlign: 'right' }}>
                  {item.matched ? '+' : ''}{item.weighted_contribution?.toFixed(1)}
                </span>
              </div>
            ))}
            {(!setup.breakdown || setup.breakdown.length === 0) && (
              <div style={{ color: 'var(--c-dim)', textAlign: 'center', fontSize: 13.2, padding: '4px 0' }}>
                No criteria found for this setup type.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ScenarioViewCard — read-only display of a saved scenario.
// ---------------------------------------------------------------------------
function ScenarioViewCard({ sc, onDelete, dateStr }) {
  const isLong = sc.setup_type?.endsWith('L');
  const badgeCls = isLong ? 'sd-setup-badge--long' : 'sd-setup-badge--short';

  return (
    <div className="sc-card" style={{ cursor: 'default', borderLeftColor: isLong ? 'var(--c-bull)' : 'var(--c-bear)' }}>
      {/* Delete button */}
      <button
        className="scenario-icon-btn scenario-icon-btn--danger"
        style={{ position: 'absolute', top: 8, right: 8 }}
        title="Delete scenario"
        onClick={() => onDelete(dateStr, sc.scenario_number)}
      >
        ×
      </button>

      {/* Header */}
      <div className="sc-card-hdr">
        <span className="sc-index">#{sc.scenario_number}</span>
        <span className={badgeCls}>{sc.setup_type}</span>
      </div>

      {/* Rationale */}
      {sc.rationale && (
        <p className="sc-rationale">{sc.rationale}</p>
      )}

      {/* Targets + Invalidation */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <div className="sc-field-label">Targets</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13.2, color: 'var(--c-text)', marginTop: 3 }}>
            {sc.targets || '—'}
          </div>
        </div>
        <div>
          <div className="sc-field-label">Invalidated If</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13.2, color: 'var(--c-bear)', marginTop: 3 }}>
            {sc.invalidated_if || '—'}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ScenarioEditForm — inline edit form for a single scenario.
// ---------------------------------------------------------------------------
function ScenarioEditForm({ sc, index, onChange, onRemove }) {
  return (
    <div style={{ background: 'var(--c-panel2)', border: '1px solid var(--c-border)', borderRadius: 8, padding: 14, position: 'relative' }}>
      <button
        className="scenario-icon-btn scenario-icon-btn--danger"
        style={{ position: 'absolute', top: 8, right: 8 }}
        onClick={() => onRemove(index)}
        title="Remove"
      >
        ×
      </button>

      <div style={{ fontSize: 13.2, fontWeight: 600, color: 'var(--c-dim)', marginBottom: 10 }}>
        Scenario #{sc.scenario_number}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Setup Type</label>
          <input
            className="sd-input"
            type="text"
            value={sc.setup_type || ''}
            onChange={e => onChange(index, 'setup_type', e.target.value)}
          />
        </div>
        <div>
          <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Targets</label>
          <input
            className="sd-input"
            type="text"
            value={sc.targets || ''}
            onChange={e => onChange(index, 'targets', e.target.value)}
          />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Rationale</label>
          <input
            className="sd-input"
            type="text"
            value={sc.rationale || ''}
            onChange={e => onChange(index, 'rationale', e.target.value)}
          />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Invalidated If</label>
          <input
            className="sd-input"
            type="text"
            value={sc.invalidated_if || ''}
            onChange={e => onChange(index, 'invalidated_if', e.target.value)}
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SessionDashboard — main page component.
// Layout mirrors Pre-market: left col (indicators) | right col (scenario +
// setups) | full-width strip below (scenario planning).
// ---------------------------------------------------------------------------
export default function SessionDashboard() {
  const {
    data,
    setupScores,
    loading,
    error,
    scenarios,
    activeSetupType,
    fetchScenarios,
    saveScenarios,
    deleteScenario,
    markActiveSetup,
  } = useLiveSession();

  const [dateStr, setDateStr] = useState(new Date().toISOString().split('T')[0]);
  const [localScenarios, setLocalScenarios] = useState([]);
  const [isEditingScenarios, setIsEditingScenarios] = useState(false);

  // Re-fetch scenarios whenever the date changes.
  useEffect(() => {
    fetchScenarios(dateStr);
  }, [fetchScenarios, dateStr]);

  // Keep local edit state in sync with server data.
  useEffect(() => {
    setLocalScenarios(scenarios || []);
  }, [scenarios]);

  // ---- Scenario CRUD helpers ----

  const handleAddScenario = () => {
    if (localScenarios.length >= 2) return;
    setLocalScenarios([
      ...localScenarios,
      {
        scenario_number: localScenarios.length + 1,
        setup_type: '',
        rationale: '',
        targets: '',
        invalidated_if: '',
      },
    ]);
  };

  const handleUpdateScenario = (index, field, value) => {
    const updated = [...localScenarios];
    updated[index] = { ...updated[index], [field]: value };
    setLocalScenarios(updated);
  };

  const handleRemoveScenario = (index) => {
    const updated = [...localScenarios];
    updated.splice(index, 1);
    // Re-sequence scenario numbers after removal.
    setLocalScenarios(updated.map((s, i) => ({ ...s, scenario_number: i + 1 })));
  };

  const handleSaveScenarios = async () => {
    try {
      await saveScenarios(dateStr, localScenarios);
      setIsEditingScenarios(false);
    } catch (e) {
      alert('Error saving scenarios: ' + e.message);
    }
  };

  const snapshot = data?.snapshot || {};
  const regime = data?.regime || {
    scenario_name: 'Unknown',
    parent_regime: '',
    subtype: '',
    confidence: 0,
  };

  const isClassified = regime.scenario_name && regime.scenario_name !== 'Unclassified';

  return (
    <div className="sd-page session-page-scaled">
      <style>{`
        .session-page-scaled .sd-scenario-name { font-size: 30.8px; }
        .session-page-scaled .sd-scenario-breadcrumb { font-size: 12.1px; }
        .session-page-scaled .sd-scenario-confidence { font-size: 12.1px; }
        .session-page-scaled .sd-setup-badge--long, .session-page-scaled .sd-setup-badge--short { font-size: 12.1px; }
        .session-page-scaled .sd-setup-scenario-num { font-size: 12.1px; }
        .session-page-scaled .sd-setup-score { font-size: 22px; }
        .session-page-scaled .sd-setup-rationale { font-size: 13.2px; }
        .session-page-scaled .sd-breakdown-toggle { font-size: 12.7px; }
        .session-page-scaled .sd-breakdown-row { font-size: 12.7px; }
        .session-page-scaled .sd-indicator-row { font-size: 14px; }
        .session-page-scaled .sd-scenario-edit-btn { font-size: 13.2px; }
        .session-page-scaled .sd-scenario-save-btn { font-size: 13.2px; }
        .session-page-scaled .sd-scenario-cancel-btn { font-size: 13.2px; }
        .session-page-scaled .sd-input { font-size: 14px; }
        .session-page-scaled .sd-date-input { font-size: 13.2px; }
        .session-page-scaled .sd-header h1 { font-size: 17.6px; }
        .session-page-scaled .sc-index { font-size: 12.7px; }
        .session-page-scaled .sc-badge { font-size: 12.7px; }
        .session-page-scaled .sc-rationale { font-size: 15.2px; }
        .session-page-scaled .sc-field-label { font-size: 12.7px; }
        .session-page-scaled .scenario-icon-btn { width: 24.2px; height: 24.2px; }
        .session-page-scaled .card-title { font-size: 12.1px; }
        .session-page-scaled .card-hdr { font-size: 12.1px; }
        .session-page-scaled .sd-active-toggle { font-size: 11px; }
        .session-page-scaled .sd-active-hint { font-size: 11.5px; }
      `}</style>
      {/* ---------------------------------------------------------------- */}
      {/* Page header                                                       */}
      {/* ---------------------------------------------------------------- */}
      <div className="sd-header">
        <h1>Live Session</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12.1, color: 'var(--c-dim)' }}>
            {loading ? 'Updating…' : `Updated ${new Date().toLocaleTimeString()}`}
          </span>
          <input
            id="sd-date-picker"
            type="date"
            value={dateStr}
            onChange={e => setDateStr(e.target.value)}
            className="sd-date-input"
          />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '8px 14px',
          background: 'var(--c-error-bg)',
          border: '1px solid var(--c-error-border)',
          borderRadius: 8,
          color: 'var(--c-error)',
          fontSize: 13,
          fontFamily: 'var(--font-mono)',
        }}>
          {error}
        </div>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* Main grid: indicators (left 360px) | scenario + setups (right)   */}
      {/* ---------------------------------------------------------------- */}
      <div className="sd-grid">

        {/* LEFT: Key Indicators */}
        <div className="sd-indicators-col">
          <div className="card">
            <CardHeader eyebrow="Key Indicators" />
            <div>
              {Object.entries(snapshot)
                .filter(([, v]) => v !== null && v !== undefined)
                .map(([key, value]) => (
                  <div key={key} className="sd-indicator-row">
                    <span className="sd-indicator-key">
                      {key.replace(/_/g, ' ')}
                    </span>
                    <span className="sd-indicator-val">
                      {typeof value === 'number' ? value.toFixed(3) : String(value)}
                    </span>
                  </div>
                ))}
              {Object.keys(snapshot).length === 0 && (
                <div style={{ color: 'var(--c-dim)', fontSize: 13.2, textAlign: 'center', padding: '16px 0', fontFamily: 'var(--font-mono)' }}>
                  Waiting for data…
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT: Active Market Scenario + Pre-Market Setups stacked */}
        <div className="sd-main-col">

          {/* Active Market Scenario */}
          <div className="card">
            <CardHeader eyebrow="Active Market Scenario" />
            <div className="sd-scenario-hero">
              <div className={`sd-scenario-name${isClassified ? ' sd-scenario-name--classified' : ''}`}>
                {regime.scenario_name || 'Unclassified'}
              </div>
              {regime.parent_regime && regime.subtype && (
                <span className="sd-scenario-breadcrumb">
                  {regime.parent_regime} › {regime.subtype}
                </span>
              )}
              <span className="sd-scenario-confidence">
                Confidence: {(regime.confidence * 100).toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Pre-Market Setups — 2-column grid so all 4 cards are visible */}
          <div className="card">
            <CardHeader eyebrow="Pre-Market Setups" />
            {/* Active setup hint — shown when a setup is marked */}
            {activeSetupType && (
              <div className="sd-active-hint">
                <span className="sd-active-dot" />
                Trading <strong>{activeSetupType}</strong> — logged to session
              </div>
            )}
            {setupScores && setupScores.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {setupScores.map((setup, idx) => (
                  <SetupScoreCard
                    key={idx}
                    setup={setup}
                    isActive={activeSetupType === setup.setup_type}
                    onMarkActive={markActiveSetup}
                  />
                ))}
              </div>
            ) : (
              <div style={{ color: 'var(--c-dim)', fontSize: 13.2, textAlign: 'center', padding: '24px 0', fontFamily: 'var(--font-mono)' }}>
                No setups planned or evaluated for today.
              </div>
            )}
          </div>

        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Full-width strip: Scenario Planning                              */}
      {/* ---------------------------------------------------------------- */}
      <div className="sd-strip">
        <div className="card">
          {/* Header + action buttons */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <CardHeader eyebrow="Scenario Planning" />
            {!isEditingScenarios ? (
              <button
                id="sd-edit-scenarios-btn"
                className="sd-scenario-edit-btn"
                onClick={() => setIsEditingScenarios(true)}
              >
                Edit Scenarios
              </button>
            ) : (
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  className="sd-scenario-cancel-btn"
                  onClick={() => {
                    setLocalScenarios(scenarios || []);
                    setIsEditingScenarios(false);
                  }}
                >
                  Cancel
                </button>
                <button
                  id="sd-save-scenarios-btn"
                  className="sd-scenario-save-btn"
                  onClick={handleSaveScenarios}
                >
                  Save
                </button>
              </div>
            )}
          </div>

          {/* Edit mode: inline forms */}
          {isEditingScenarios ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {localScenarios.map((sc, index) => (
                <ScenarioEditForm
                  key={index}
                  sc={sc}
                  index={index}
                  onChange={handleUpdateScenario}
                  onRemove={handleRemoveScenario}
                />
              ))}
              {localScenarios.length < 2 && (
                <button
                  className="sc-add-btn"
                  onClick={handleAddScenario}
                >
                  + Add Scenario
                </button>
              )}
            </div>
          ) : (
            /* Read mode: scenario tiles span full width equally */
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
              {scenarios && scenarios.length > 0 ? (
                scenarios.map(sc => (
                  <div key={sc.id} style={{ position: 'relative' }}>
                    <ScenarioViewCard
                      sc={sc}
                      dateStr={dateStr}
                      onDelete={deleteScenario}
                    />
                  </div>
                ))
              ) : (
                <div style={{ color: 'var(--c-dim)', fontSize: 13.2, textAlign: 'center', padding: '24px 0', fontFamily: 'var(--font-mono)' }}>
                  No scenarios planned for today.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
