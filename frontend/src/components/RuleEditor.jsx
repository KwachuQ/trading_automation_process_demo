import React, { useState, useEffect } from 'react';
import { X, Plus, Trash2 } from 'lucide-react';

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

export default function RuleEditor({ rule, onSave, onCancel }) {
  const [formData, setFormData] = useState({
    name: '',
    characteristics: '',
    risk_adjustments: {
      position_size_modifier: 1.0,
      expected_range: '',
      execution_style: ''
    },
    is_active: true,
    parent_regime: '',
    subtype: '',
    conditions: []
  });

  useEffect(() => {
    if (rule) {
      setFormData({
        name: rule.name || '',
        characteristics: rule.characteristics || '',
        risk_adjustments: {
          position_size_modifier: rule.risk_adjustments?.position_size_modifier ?? 1.0,
          expected_range: rule.risk_adjustments?.expected_range || '',
          execution_style: rule.risk_adjustments?.execution_style || ''
        },
        is_active: rule.is_active ?? true,
        parent_regime: rule.parent_regime || '',
        subtype: rule.subtype || '',
        conditions: rule.conditions ? [...rule.conditions] : []
      });
    } else {
      setFormData({
        name: '',
        characteristics: '',
        risk_adjustments: {
          position_size_modifier: 1.0,
          expected_range: '',
          execution_style: ''
        },
        is_active: true,
        parent_regime: '',
        subtype: '',
        conditions: []
      });
    }
  }, [rule]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleRiskChange = (e) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      risk_adjustments: {
        ...prev.risk_adjustments,
        [name]: type === 'number' ? Number(value) : value
      }
    }));
  };

  const addCondition = () => {
    setFormData(prev => ({
      ...prev,
      conditions: [...prev.conditions, { indicator: 'trend_weekly', operator: '==', value: '', weight: 1.0 }]
    }));
  };

  const removeCondition = (index) => {
    setFormData(prev => ({
      ...prev,
      conditions: prev.conditions.filter((_, i) => i !== index)
    }));
  };

  const updateCondition = (index, field, val) => {
    setFormData(prev => {
      const newConditions = [...prev.conditions];
      
      let finalVal = val;
      if (field === 'weight') {
        finalVal = Number(val);
      }
      
      newConditions[index] = {
        ...newConditions[index],
        [field]: finalVal
      };

      // If switching to an "in" operator or to a numeric field, we don't automatically convert val here, 
      // but we could. For simplicity, we just save what the user types.

      return {
        ...prev,
        conditions: newConditions
      };
    });
  };

  const renderValueInput = (cond, index) => {
    const isEnum = !!ENUM_OPTIONS[cond.indicator];
    const isNumericField = !isEnum;
    const isList = cond.operator === 'in';
    const isBetween = cond.operator === 'between';

    if (isBetween) {
      const currentArray = Array.isArray(cond.value) ? cond.value : ['', ''];
      const [minVal, maxVal] = currentArray;
      return (
        <div className="flex gap-2 items-center">
          <input
            type="number" step="any" placeholder="Min"
            className="w-1/2 px-2 py-1 bg-gray-800 border border-gray-600 rounded text-sm text-gray-100 placeholder-gray-500"
            value={minVal !== undefined && minVal !== null ? minVal : ''}
            onChange={e => {
              const newMin = e.target.value === '' ? '' : Number(e.target.value);
              const curr = Array.isArray(cond.value) ? [...cond.value] : ['', ''];
              curr[0] = newMin;
              updateCondition(index, 'value', curr);
            }}
          />
          <span className="text-gray-400 text-xs">to</span>
          <input
            type="number" step="any" placeholder="Max"
            className="w-1/2 px-2 py-1 bg-gray-800 border border-gray-600 rounded text-sm text-gray-100 placeholder-gray-500"
            value={maxVal !== undefined && maxVal !== null ? maxVal : ''}
            onChange={e => {
              const newMax = e.target.value === '' ? '' : Number(e.target.value);
              const curr = Array.isArray(cond.value) ? [...cond.value] : ['', ''];
              curr[1] = newMax;
              updateCondition(index, 'value', curr);
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
            className="w-full px-2 py-1 bg-gray-800 border border-gray-600 rounded text-sm text-gray-100"
            value={Array.isArray(cond.value) ? cond.value : (typeof cond.value === 'string' && cond.value ? cond.value.split(',').map(s=>s.trim()) : [])}
            onChange={(e) => {
              const opts = Array.from(e.target.selectedOptions, option => option.value);
              updateCondition(index, 'value', opts);
            }}
          >
            {ENUM_OPTIONS[cond.indicator].map(opt => <option key={opt} value={opt}>{opt}</option>)}
          </select>
        );
      }
      return (
        <input
          type="text"
          className="w-full px-2 py-1 bg-gray-800 border border-gray-600 rounded text-sm text-gray-100"
          value={Array.isArray(cond.value) ? cond.value.join(', ') : cond.value}
          onChange={(e) => updateCondition(index, 'value', e.target.value)}
          placeholder="value1, value2"
        />
      );
    }

    if (isEnum) {
      return (
        <select
          className="w-full px-2 py-1 bg-gray-800 border border-gray-600 rounded text-sm text-gray-100"
          value={cond.value}
          onChange={(e) => updateCondition(index, 'value', e.target.value)}
        >
          <option value="" disabled>Select a value...</option>
          {ENUM_OPTIONS[cond.indicator].map(opt => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      );
    }

    return (
      <input
        type="number"
        step="any"
        className="w-full px-2 py-1 bg-gray-800 border border-gray-600 rounded text-sm text-gray-100"
        value={cond.value}
        onChange={(e) => updateCondition(index, 'value', Number(e.target.value))}
      />
    );
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    // Validate 'between' fields have both min and max
    for (const c of formData.conditions) {
      if (c.operator === 'between') {
        if (!Array.isArray(c.value) || c.value.length !== 2 || c.value[0] === '' || c.value[1] === '' || c.value[0] === undefined || c.value[1] === undefined) {
          alert(`Please specify both Min and Max for indicator ${c.indicator} in the between range.`);
          return;
        }
      }
    }

    // Parse 'in' array if needed
    const payload = {
      ...formData,
      conditions: formData.conditions.map(c => {
        let val = c.value;
        if (c.operator === 'in' && typeof val === 'string') {
          val = val.split(',').map(s => s.trim().replace(/^['"](.*)['"]$/, '$1')).filter(Boolean);
        } else if (c.operator === 'between') {
          if (Array.isArray(val)) {
            val = [val[0] === '' ? 0 : Number(val[0]), val[1] === '' ? 0 : Number(val[1])];
          }
        }
        return { ...c, value: val };
      })
    };
    onSave(payload);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto border border-gray-700 flex flex-col">
        <div className="flex justify-between items-center px-6 py-4 border-b border-gray-700 sticky top-0 bg-gray-900 z-10">
          <h2 className="text-xl font-semibold text-gray-100">{rule ? 'Edit Scenario' : 'New Scenario'}</h2>
          <button onClick={onCancel} className="text-gray-400 hover:text-white">
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6 flex-1">
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Name</label>
                <input
                  type="text"
                  name="name"
                  required
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  value={formData.name}
                  onChange={handleChange}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Characteristics</label>
                <textarea
                  name="characteristics"
                  rows={2}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  value={formData.characteristics}
                  onChange={handleChange}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Parent Regime</label>
                  <input
                    type="text"
                    name="parent_regime"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={formData.parent_regime}
                    onChange={handleChange}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Subtype</label>
                  <input
                    type="text"
                    name="subtype"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={formData.subtype}
                    onChange={handleChange}
                  />
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  name="is_active"
                  id="is_active"
                  checked={formData.is_active}
                  onChange={handleChange}
                  className="w-4 h-4 text-blue-600 bg-gray-800 border-gray-700 rounded focus:ring-blue-500"
                />
                <label htmlFor="is_active" className="text-sm font-medium text-gray-300">Active</label>
              </div>
            </div>

            <div className="space-y-4 p-4 bg-gray-800/50 border border-gray-700 rounded-lg">
              <h3 className="text-sm font-medium text-gray-200">Risk Adjustments</h3>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Position Size Modifier (0 - 2)</label>
                <input
                  type="number"
                  name="position_size_modifier"
                  min="0" max="2" step="0.1"
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  value={formData.risk_adjustments.position_size_modifier}
                  onChange={handleRiskChange}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Expected Range</label>
                <input
                  type="text"
                  name="expected_range"
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  value={formData.risk_adjustments.expected_range}
                  onChange={handleRiskChange}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Execution Style</label>
                <input
                  type="text"
                  name="execution_style"
                  className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  value={formData.risk_adjustments.execution_style}
                  onChange={handleRiskChange}
                />
              </div>
            </div>
          </div>

          <div>
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-medium text-gray-200">Conditions</h3>
              <button
                type="button"
                onClick={addCondition}
                className="flex items-center space-x-1 text-sm text-blue-400 hover:text-blue-300"
              >
                <Plus className="w-4 h-4" />
                <span>Add Condition</span>
              </button>
            </div>
            
            {formData.conditions.length === 0 && (
              <p className="text-sm text-gray-500 italic py-4 text-center border border-dashed border-gray-700 rounded">
                No conditions added.
              </p>
            )}

            <div className="space-y-2">
              {formData.conditions.map((cond, index) => (
                <div key={index} className="flex items-start gap-2 bg-gray-800 p-2 rounded border border-gray-700">
                  <div className="flex-1">
                    <select
                      className="w-full px-2 py-1 bg-gray-900 border border-gray-600 rounded text-sm text-gray-100"
                      value={cond.indicator}
                      onChange={(e) => updateCondition(index, 'indicator', e.target.value)}
                    >
                      {INDICATORS.map(ind => <option key={ind} value={ind}>{ind}</option>)}
                    </select>
                  </div>
                  <div className="w-20">
                    <select
                      className="w-full px-2 py-1 bg-gray-900 border border-gray-600 rounded text-sm text-gray-100 text-center"
                      value={cond.operator}
                      onChange={(e) => {
                        const op = e.target.value;
                        updateCondition(index, 'operator', op);
                        updateCondition(index, 'value', op === 'between' ? ['', ''] : (op === 'in' ? [] : ''));
                      }}
                    >
                      {OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                    </select>
                  </div>
                  <div className="flex-1">
                    {renderValueInput(cond, index)}
                  </div>
                  <div className="w-20">
                    <input
                      type="number"
                      min="0.1"
                      step="0.1"
                      className="w-full px-2 py-1 bg-gray-900 border border-gray-600 rounded text-sm text-gray-100 text-center"
                      value={cond.weight}
                      onChange={(e) => updateCondition(index, 'weight', e.target.value)}
                      placeholder="Wt"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => removeCondition(index)}
                    className="p-1 text-gray-500 hover:text-red-400 mt-0.5"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end space-x-3 pt-4 border-t border-gray-700 sticky bottom-0 bg-gray-900 pb-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm font-medium text-gray-300 bg-gray-800 border border-gray-600 rounded hover:bg-gray-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700"
            >
              Save Scenario
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
