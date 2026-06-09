import React, { useState } from 'react';
import { Plus, Edit2, Trash2 } from 'lucide-react';
import { useFeatureStore } from '../hooks/useFeatureStore';
import RuleEditor from '../components/RuleEditor';

const INDICATORS = [
  'trend_yearly', 'trend_quarterly', 'trend_monthly', 'trend_weekly',
  'band_position_yearly', 'band_position_quarterly', 'band_position_monthly', 'band_position_weekly',
  'adr', 'adr_slope', 'rvol', 'rvol_slope', 'vvix_vix_ratio',
  'delta_slope', 'gamma_regime', 'vwap_slope', 'cd_vs_ma', 'vol_regime'
];
const ENUM_OPTIONS = {
  trend_yearly: ['rising', 'sideways', 'falling'],
  trend_quarterly: ['rising', 'sideways', 'falling'],
  trend_monthly: ['rising', 'sideways', 'falling'],
  trend_weekly: ['rising', 'sideways', 'falling'],
  band_position_yearly: ['Imbalance up', 'Imbalance down', 'Inside value area'],
  band_position_quarterly: ['Imbalance up', 'Imbalance down', 'Inside value area'],
  band_position_monthly: ['Imbalance up', 'Imbalance down', 'Inside value area'],
  band_position_weekly: ['Imbalance up', 'Imbalance down', 'Inside value area'],
  adr_slope: ['rising', 'sideways', 'falling'],
  rvol_slope: ['rising', 'sideways', 'falling'],
  delta_slope: ['rising', 'sideways', 'falling'],
  gamma_regime: ['positive', 'negative', 'mixed'],
  vwap_slope: ['rising', 'sideways', 'falling'],
  cd_vs_ma: ['above MA', 'below MA'],
  vol_regime: ['EXTREME', 'HIGH', 'MODERATE', 'LOW', 'VERY_LOW']
};
const OPERATORS = ['>', '<', '>=', '<=', '==', '!=', 'in', 'between'];

export default function FeatureStorePage() {
  const {
    marketScenarios,
    scoringCriteria,
    setupTypeFilter,
    setSetupTypeFilter,
    loading,
    error,
    createScenario,
    updateScenario,
    deleteScenario,
    createCriterion,
    updateCriterion,
    deleteCriterion
  } = useFeatureStore();

  const [editingScenario, setEditingScenario] = useState(null);
  const [isScenarioEditorOpen, setIsScenarioEditorOpen] = useState(false);

  // Simple state for inline creation of scoring criterion
  const [newCriterion, setNewCriterion] = useState({
    name: '',
    setup_type: 'ML',
    weight: 1.0,
    is_active: true,
    condition: { indicator: 'trend_weekly', operator: '==', value: '', weight: 1.0 }
  });
  const [isAddingCriterion, setIsAddingCriterion] = useState(false);

  const handleOpenScenarioEditor = (scenario = null) => {
    setEditingScenario(scenario);
    setIsScenarioEditorOpen(true);
  };

  const handleCloseScenarioEditor = () => {
    setEditingScenario(null);
    setIsScenarioEditorOpen(false);
  };

  const handleSaveScenario = async (payload) => {
    try {
      if (editingScenario?.id) {
        await updateScenario(editingScenario.id, payload);
      } else {
        await createScenario(payload);
      }
      handleCloseScenarioEditor();
    } catch (e) {
      alert(e.message || 'Error saving scenario');
    }
  };

  const handleDeleteScenario = async (id) => {
    if (window.confirm('Delete this market scenario?')) {
      try {
        await deleteScenario(id);
      } catch (e) {
        alert(e.message || 'Error deleting scenario');
      }
    }
  };

  const handleToggleScenarioActive = async (scenario) => {
    try {
      await updateScenario(scenario.id, { ...scenario, is_active: !scenario.is_active });
    } catch (e) {
      alert(e.message || 'Error updating scenario');
    }
  };

  const handleToggleCriterionActive = async (crit) => {
    try {
      await updateCriterion(crit.id, { ...crit, is_active: !crit.is_active });
    } catch (e) {
      alert(e.message || 'Error updating criterion');
    }
  };

  const handleDeleteCriterion = async (id) => {
    if (window.confirm('Delete this scoring criterion?')) {
      try {
        await deleteCriterion(id);
      } catch (e) {
        alert(e.message || 'Error deleting criterion');
      }
    }
  };

  const handleSaveCriterion = async () => {
    if (!newCriterion.name) {
      alert('Please fill out a name for the scoring criterion.');
      return;
    }

    const isBetween = newCriterion.condition.operator === 'between';
    if (isBetween) {
      const val = newCriterion.condition.value;
      if (!Array.isArray(val) || val.length !== 2 || val[0] === '' || val[1] === '' || val[0] === undefined || val[1] === undefined) {
        alert('Please specify both Min and Max for the between range.');
        return;
      }
    } else if (newCriterion.condition.value === undefined || newCriterion.condition.value === null || newCriterion.condition.value === '') {
      alert('Please specify a condition value.');
      return;
    }

    try {
      let val = newCriterion.condition.value;
      if (newCriterion.condition.operator === 'in' && typeof val === 'string') {
        val = val.split(',').map(s => s.trim().replace(/^['"](.*)['"]$/, '$1')).filter(Boolean);
      } else if (newCriterion.condition.operator === 'between') {
        // Cast range bounds to numbers
        if (Array.isArray(val)) {
          val = [val[0] === '' ? 0 : Number(val[0]), val[1] === '' ? 0 : Number(val[1])];
        }
      } else if (typeof val === 'string' && !isNaN(Number(val)) && newCriterion.condition.operator !== 'in') {
        // Basic attempt to convert to number if it's purely numeric and is a string
        const numVal = Number(val);
        if (numVal.toString() === val.trim()) val = numVal;
      }

      const payload = {
        ...newCriterion,
        condition: { ...newCriterion.condition, value: val }
      };

      await createCriterion(payload);
      setIsAddingCriterion(false);
      setNewCriterion({
        name: '',
        setup_type: 'ML',
        weight: 1.0,
        is_active: true,
        condition: { indicator: 'trend_weekly', operator: '==', value: '', weight: 1.0 }
      });
    } catch (e) {
      alert(e.message || 'Error saving criterion');
    }
  };

  return (
    <div className="sd-page feature-store-page-scaled">
      <style>{`
        .feature-store-page-scaled .sd-header h1 { font-size: 19.2px; }
        .feature-store-page-scaled .card-title { font-size: 13.2px; }
        .feature-store-page-scaled .sc-add-btn { font-size: 15.2px; padding: 8px 14px; }
        .feature-store-page-scaled .wl-table th { font-size: 13.2px; padding: 7px 10px; }
        .feature-store-page-scaled .wl-table td { font-size: 14.4px; padding: 8px 10px; }
        .feature-store-page-scaled .sc-badge { font-size: 13.8px; padding: 2px 8px; }
        .feature-store-page-scaled .segment-opt { font-size: 14.4px; padding: 5px 16px; }
        .feature-store-page-scaled .sc-field-label { font-size: 13.8px; }
        .feature-store-page-scaled .sd-input { font-size: 15.2px; padding: 7px 12px; }
        .feature-store-page-scaled .sd-scenario-save-btn { font-size: 14.4px; padding: 6px 16px; }
        .feature-store-page-scaled .scenario-icon-btn { width: 26.4px; height: 26.4px; }
      `}</style>
      <div className="sd-header">
        <h1>Feature Store</h1>
        {loading && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13.2, color: 'var(--c-dim)' }}>Loading...</span>}
      </div>

      {error && (
        <div style={{ padding: '8px 14px', background: 'var(--c-error-bg)', border: '1px solid var(--c-error-border)', borderRadius: 8, color: 'var(--c-error)', fontSize: 15.6, fontFamily: 'var(--font-mono)' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Market Scenarios Section */}
        <section className="card">
          <div className="card-hdr">
            <div className="card-title">Market Scenarios</div>
            <button
              onClick={() => handleOpenScenarioEditor()}
              className="sc-add-btn"
              style={{ margin: 0 }}
            >
              <Plus className="w-4 h-4" /> Add Scenario
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="wl-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Parent Regime</th>
                  <th>Subtype</th>
                  <th>Conditions</th>
                  <th>Active</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {marketScenarios.length === 0 ? (
                  <tr><td colSpan="6" style={{ textAlign: 'center', color: 'var(--c-dim)' }}>No market scenarios found.</td></tr>
                ) : (
                  marketScenarios.map((scenario) => (
                    <tr key={scenario.id}>
                      <td style={{ color: 'var(--c-text)', fontWeight: 500, fontFamily: 'var(--font-ui)' }}>{scenario.name}</td>
                      <td>{scenario.parent_regime}</td>
                      <td>{scenario.subtype}</td>
                      <td>{scenario.conditions?.length || 0}</td>
                      <td>
                        <button
                           onClick={() => handleToggleScenarioActive(scenario)}
                           className={`sc-badge ${scenario.is_active ? 'sc-badge--bull' : ''}`}
                           style={{ cursor: 'pointer', opacity: scenario.is_active ? 1 : 0.6 }}
                        >
                           {scenario.is_active ? 'Active' : 'Inactive'}
                        </button>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button onClick={() => handleOpenScenarioEditor(scenario)} className="scenario-icon-btn" style={{ display: 'inline-flex', marginRight: 4 }}>
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleDeleteScenario(scenario.id)} className="scenario-icon-btn scenario-icon-btn--danger" style={{ display: 'inline-flex' }}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Scoring Criteria Section */}
        <section className="card">
          <div className="card-hdr" style={{ marginBottom: isAddingCriterion ? 0 : 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div className="card-title" style={{ marginBottom: 0 }}>Scoring Criteria</div>
              <div className="segment-ctrl">
                {['All', 'ML', 'MS', 'MRL', 'MRS'].map(tab => (
                  <button
                    key={tab}
                    onClick={() => setSetupTypeFilter(tab)}
                    className={`segment-opt ${setupTypeFilter === tab ? 'active' : ''}`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            </div>
            <button
              onClick={() => setIsAddingCriterion(!isAddingCriterion)}
              className="sc-add-btn"
              style={{ margin: 0 }}
            >
              <Plus className="w-4 h-4" /> {isAddingCriterion ? 'Cancel' : 'Add Criterion'}
            </button>
          </div>

          {isAddingCriterion && (
            <div style={{ padding: '14px 0', borderBottom: '1px solid var(--c-border)', marginBottom: 14 }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
                <div style={{ flex: 1 }}>
                  <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Name</label>
                  <input
                    type="text"
                    className="sd-input"
                    value={newCriterion.name}
                    onChange={e => setNewCriterion(prev => ({ ...prev, name: e.target.value }))}
                  />
                </div>
                <div style={{ width: 80 }}>
                  <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Setup</label>
                  <select
                    className="sd-input"
                    value={newCriterion.setup_type}
                    onChange={e => setNewCriterion(prev => ({ ...prev, setup_type: e.target.value }))}
                  >
                    <option value="ML">ML</option>
                    <option value="MS">MS</option>
                    <option value="MRL">MRL</option>
                    <option value="MRS">MRS</option>
                  </select>
                </div>
                <div>
                  <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Indicator</label>
                  <select
                    className="sd-input"
                    value={newCriterion.condition.indicator}
                    onChange={e => setNewCriterion(prev => ({ ...prev, condition: { ...prev.condition, indicator: e.target.value } }))}
                  >
                    {INDICATORS.map(ind => <option key={ind} value={ind}>{ind}</option>)}
                  </select>
                </div>
                <div style={{ width: 80 }}>
                  <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Op</label>
                  <select
                    className="sd-input"
                    value={newCriterion.condition.operator}
                    onChange={e => {
                      const op = e.target.value;
                      setNewCriterion(prev => ({
                        ...prev,
                        condition: {
                          ...prev.condition,
                          operator: op,
                          value: op === 'between' ? ['', ''] : (op === 'in' ? [] : '')
                        }
                      }));
                    }}
                  >
                    {OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Value</label>
                  {(() => {
                    const isEnum = !!ENUM_OPTIONS[newCriterion.condition.indicator];
                    const isList = newCriterion.condition.operator === 'in';
                    const isBetween = newCriterion.condition.operator === 'between';

                    if (isBetween) {
                      const currentArray = Array.isArray(newCriterion.condition.value) ? newCriterion.condition.value : ['', ''];
                      const [minVal, maxVal] = currentArray;
                      return (
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <input
                            type="number" step="any" placeholder="Min"
                            className="sd-input"
                            style={{ flex: 1 }}
                            value={minVal !== undefined && minVal !== null ? minVal : ''}
                            onChange={e => {
                              const newMin = e.target.value === '' ? '' : Number(e.target.value);
                              setNewCriterion(prev => {
                                const curr = Array.isArray(prev.condition.value) ? [...prev.condition.value] : ['', ''];
                                curr[0] = newMin;
                                return { ...prev, condition: { ...prev.condition, value: curr } };
                              });
                            }}
                          />
                          <span style={{ color: 'var(--c-dim)', fontSize: 13.2 }}>to</span>
                          <input
                            type="number" step="any" placeholder="Max"
                            className="sd-input"
                            style={{ flex: 1 }}
                            value={maxVal !== undefined && maxVal !== null ? maxVal : ''}
                            onChange={e => {
                              const newMax = e.target.value === '' ? '' : Number(e.target.value);
                              setNewCriterion(prev => {
                                const curr = Array.isArray(prev.condition.value) ? [...prev.condition.value] : ['', ''];
                                curr[1] = newMax;
                                return { ...prev, condition: { ...prev.condition, value: curr } };
                              });
                            }}
                          />
                        </div>
                      );
                    }
                    
                    if (isList) {
                      if (isEnum) {
                        return (
                          <select
                            multiple
                            className="sd-input"
                            value={Array.isArray(newCriterion.condition.value) ? newCriterion.condition.value : (typeof newCriterion.condition.value === 'string' && newCriterion.condition.value ? newCriterion.condition.value.split(',').map(s=>s.trim()) : [])}
                            onChange={e => {
                              const opts = Array.from(e.target.selectedOptions, option => option.value);
                              setNewCriterion(prev => ({ ...prev, condition: { ...prev.condition, value: opts } }));
                            }}
                          >
                            {ENUM_OPTIONS[newCriterion.condition.indicator].map(opt => <option key={opt} value={opt}>{opt}</option>)}
                          </select>
                        );
                      }
                      return (
                        <input
                          type="text"
                          className="sd-input"
                          value={Array.isArray(newCriterion.condition.value) ? newCriterion.condition.value.join(', ') : newCriterion.condition.value}
                          onChange={e => setNewCriterion(prev => ({ ...prev, condition: { ...prev.condition, value: e.target.value } }))}
                        />
                      );
                    }

                    if (isEnum) {
                      return (
                        <select
                          className="sd-input"
                          value={newCriterion.condition.value}
                          onChange={e => setNewCriterion(prev => ({ ...prev, condition: { ...prev.condition, value: e.target.value } }))}
                        >
                          <option value="" disabled>Select a value...</option>
                          {ENUM_OPTIONS[newCriterion.condition.indicator].map(opt => <option key={opt} value={opt}>{opt}</option>)}
                        </select>
                      );
                    }

                    return (
                      <input
                        type="number" step="any"
                        className="sd-input"
                        value={newCriterion.condition.value}
                        onChange={e => setNewCriterion(prev => ({ ...prev, condition: { ...prev.condition, value: Number(e.target.value) } }))}
                      />
                    );
                  })()}
                </div>
                <div style={{ width: 60 }}>
                  <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>C.Wt</label>
                  <input
                    type="number" step="0.1"
                    className="sd-input"
                    value={newCriterion.condition.weight}
                    onChange={e => setNewCriterion(prev => ({ ...prev, condition: { ...prev.condition, weight: Number(e.target.value) } }))}
                  />
                </div>
                <div style={{ width: 60 }}>
                  <label className="sc-field-label" style={{ display: 'block', marginBottom: 4 }}>Wt</label>
                  <input
                    type="number" step="0.1"
                    className="sd-input"
                    value={newCriterion.weight}
                    onChange={e => setNewCriterion(prev => ({ ...prev, weight: Number(e.target.value) }))}
                  />
                </div>
                <button
                  onClick={handleSaveCriterion}
                  className="sd-scenario-save-btn"
                  style={{ height: 32 }}
                >
                  Save
                </button>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="wl-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Condition Summary</th>
                  <th>Weight</th>
                  <th>Active</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {scoringCriteria.length === 0 ? (
                  <tr><td colSpan="5" style={{ textAlign: 'center', color: 'var(--c-dim)' }}>No scoring criteria found.</td></tr>
                ) : (
                  scoringCriteria.map((crit) => (
                    <tr key={crit.id}>
                      <td style={{ color: 'var(--c-text)', fontWeight: 500, fontFamily: 'var(--font-ui)' }}>{crit.name}</td>
                      <td style={{ color: 'var(--c-muted)' }}>
                        {crit.condition?.indicator} {crit.condition?.operator} {Array.isArray(crit.condition?.value) ? (crit.condition.operator === 'between' ? `${crit.condition.value[0]} to ${crit.condition.value[1]}` : `[${crit.condition.value.join(', ')}]`) : crit.condition?.value}
                      </td>
                      <td>{crit.weight}</td>
                      <td>
                        <button
                          onClick={() => handleToggleCriterionActive(crit)}
                          className={`sc-badge ${crit.is_active ? 'sc-badge--bull' : ''}`}
                          style={{ cursor: 'pointer', opacity: crit.is_active ? 1 : 0.6 }}
                        >
                          {crit.is_active ? 'Active' : 'Inactive'}
                        </button>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button onClick={() => handleDeleteCriterion(crit.id)} className="scenario-icon-btn scenario-icon-btn--danger" style={{ display: 'inline-flex' }}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {isScenarioEditorOpen && (
        <RuleEditor
          rule={editingScenario}
          onSave={handleSaveScenario}
          onCancel={handleCloseScenarioEditor}
        />
      )}
    </div>
  );
}
