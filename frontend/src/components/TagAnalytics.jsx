import React, { useState, useEffect, useMemo } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell
} from 'recharts';
import { useReview } from '../hooks/useReview';
import { t, CardHeader } from './ui';

export default function TagAnalytics({ dateFrom, dateTo }) {
  const { loadStatsByTag } = useReview();
  const [setupStats, setSetupStats] = useState(null);
  const [indicatorStats, setIndicatorStats] = useState(null);
  const [loading, setLoading] = useState(true);

  // local control states
  const [activeDataset, setActiveDataset] = useState('setup_tag'); // 'setup_tag' | 'key_indicators_tags'
  const [chartType, setChartType] = useState('bar'); // 'bar' | 'pie' | 'line'
  const [selectedMetric, setSelectedMetric] = useState('total_pnl'); // 'total_pnl' | 'win_rate' | 'total_trades' | 'profit_factor'
  const [searchText, setSearchText] = useState('');
  const [minTrades, setMinTrades] = useState('');

  // Table sorting state
  const [sortField, setSortField] = useState(null);
  const [sortAsc, setSortAsc] = useState(false);

  // Fetch tag stats on mount/date changes
  useEffect(() => {
    let mounted = true;
    const fetchStats = async () => {
      setLoading(true);
      try {
        const [setupRes, indRes] = await Promise.all([
          loadStatsByTag('setup_tag', { date_from: dateFrom, date_to: dateTo }),
          loadStatsByTag('key_indicators_tags', { date_from: dateFrom, date_to: dateTo })
        ]);
        if (mounted) {
          setSetupStats(setupRes);
          setIndicatorStats(indRes);
        }
      } catch (err) {
        console.error(err);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchStats();
    return () => {
      mounted = false;
    };
  }, [loadStatsByTag, dateFrom, dateTo]);

  // Format metric value helper
  const formatValue = (value, metric) => {
    if (value === undefined || value === null) return 'N/A';
    if (metric === 'total_pnl') {
      return value >= 0 ? `$${value.toFixed(2)}` : `-$${Math.abs(value).toFixed(2)}`;
    }
    if (metric === 'win_rate') {
      return `${value.toFixed(1)}%`;
    }
    if (metric === 'profit_factor') {
      return value.toFixed(2);
    }
    return value.toString();
  };

  // Metric label helper
  const getMetricLabel = (metric) => {
    switch (metric) {
      case 'total_pnl': return 'Total P&L';
      case 'win_rate': return 'Win Rate';
      case 'total_trades': return 'Trades';
      case 'profit_factor': return 'Profit Factor';
      default: return metric;
    }
  };

  // Formatter for tag names/labels (specifically key indicator groups)
  const formatTagLabel = (label, forChart = false) => {
    if (!label) return '';
    const formatted = label.split(',').map(s => s.trim()).join(' • ');
    if (forChart && formatted.length > 15) {
      return formatted.substring(0, 12) + '...';
    }
    return formatted;
  };

  // Local filter logic
  const filteredData = useMemo(() => {
    const rawStats = activeDataset === 'setup_tag' ? setupStats : indicatorStats;
    if (!rawStats) return [];

    return Object.entries(rawStats)
      .map(([tag, data]) => ({
        name: tag, // Raw tag name as unique identifier
        total_pnl: data.summary.total_pnl ?? 0,
        win_rate: data.summary.win_rate ?? 0,
        total_trades: data.summary.total_trades ?? 0,
        profit_factor: data.summary.profit_factor ?? 0
      }))
      .filter(item => {
        // Tag search filter
        if (searchText) {
          const query = searchText.toLowerCase();
          if (!item.name.toLowerCase().includes(query)) {
            return false;
          }
        }
        // Min trades filter
        if (minTrades) {
          const minVal = parseInt(minTrades, 10);
          if (!isNaN(minVal) && item.total_trades < minVal) {
            return false;
          }
        }
        return true;
      });
  }, [setupStats, indicatorStats, activeDataset, searchText, minTrades]);

  // Derived sorted table rows
  const sortedData = useMemo(() => {
    const field = sortField || selectedMetric;
    return [...filteredData].sort((a, b) => {
      const aVal = a[field];
      const bVal = b[field];
      if (sortAsc) {
        return aVal > bVal ? 1 : -1;
      } else {
        return aVal < bVal ? 1 : -1;
      }
    });
  }, [filteredData, selectedMetric, sortField, sortAsc]);

  // Sort handler for table headers
  const handleSort = (field) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false); // default desc
    }
  };

  // Loading state placeholder
  if (loading) {
    return (
      <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 300 }}>
        <span style={{ fontFamily: t.mono, fontSize: 12.5, color: t.dim }} className="badge-running">
          Computing tag analytics...
        </span>
      </div>
    );
  }

  // Recharts Custom Tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const dataObj = payload[0].payload;
      const rawLabel = dataObj?.fullName || label || payload[0].name;
      const realValue = dataObj && 'realValue' in dataObj ? dataObj.realValue : payload[0].value;

      return (
        <div style={{
          background: t.panel2,
          border: `1px solid ${t.border}`,
          borderRadius: '6px',
          padding: '10px 14px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)'
        }}>
          <p style={{ margin: '0 0 6px', fontSize: 12, fontWeight: 600, color: t.muted }}>{rawLabel}</p>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 20, fontSize: 13, fontFamily: t.ui }}>
            <span style={{ color: t.muted }}>{getMetricLabel(selectedMetric)}:</span>
            <span style={{
              fontFamily: t.mono,
              fontWeight: 700,
              color: selectedMetric === 'total_pnl' ? (realValue >= 0 ? t.bull : t.bear) : '#ffffff'
            }}>
              {formatValue(realValue, selectedMetric)}
            </span>
          </div>
        </div>
      );
    }
    return null;
  };

  // Header render helper with sort indicator
  const renderHeader = (label, field, isNumeric = false) => {
    const isCurrent = (sortField || selectedMetric) === field;
    const arrow = isCurrent ? (sortAsc ? ' ▲' : ' ▼') : '';
    return (
      <th
        onClick={() => handleSort(field)}
        style={{
          padding: '8px 12px',
          textAlign: isNumeric ? 'right' : 'left',
          cursor: 'pointer',
          userSelect: 'none',
          color: isCurrent ? t.text : t.muted,
          borderBottom: `1px solid ${t.border}`,
          fontWeight: 600,
          width: field === 'name' ? '40%' : '15%'
        }}
      >
        {label}{arrow}
      </th>
    );
  };

  // Recharts Chart Renderer based on local controls
  const renderChart = () => {
    const isPie = chartType === 'pie';
    const isLine = chartType === 'line';

    if (isPie) {
      const hasNegative = sortedData.some(d => d[selectedMetric] < 0);
      const chartData = sortedData.map(d => ({
        name: formatTagLabel(d.name, true),
        fullName: d.name,
        value: Math.abs(d[selectedMetric]),
        realValue: d[selectedMetric]
      }));

      const COLORS = [
        'var(--c-accent)',
        '#8884d8',
        '#83a6ed',
        '#8dd1e1',
        '#82ca9d',
        '#a4de6c',
        '#d0ed57',
        '#ffc658'
      ];

      return (
        <div style={{ position: 'relative', width: '100%', height: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                labelLine={true}
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          {hasNegative && (
            <div style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              textAlign: 'center',
              fontSize: 10,
              color: t.warning,
              fontFamily: t.ui
            }}>
              * Absolute values used for negative P&L in Pie chart.
            </div>
          )}
        </div>
      );
    }

    // Default to Bar Chart
    const chartData = sortedData.map(d => ({
      name: formatTagLabel(d.name, true),
      fullName: d.name,
      value: d[selectedMetric]
    }));

    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
          <CartesianGrid stroke="rgba(255, 255, 255, 0.03)" strokeDasharray="3 3" />
          <XAxis dataKey="name" stroke={t.dim} tick={{ fill: t.muted, fontSize: 10, fontFamily: t.mono }} />
          <YAxis stroke={t.dim} tick={{ fill: t.muted, fontSize: 10, fontFamily: t.mono }} tickFormatter={(val) => formatValue(val, selectedMetric)} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255, 255, 255, 0.02)' }} />
          <Bar dataKey="value" name={getMetricLabel(selectedMetric)}>
            {chartData.map((entry, index) => {
              const val = entry.value;
              const fill = selectedMetric === 'total_pnl'
                ? (val >= 0 ? t.bullSoft : t.bearSoft)
                : 'var(--c-accent-dim)';
              const stroke = selectedMetric === 'total_pnl'
                ? (val >= 0 ? t.bullBorder : t.bearBorder)
                : 'var(--c-accent)';
              return <Cell key={`cell-${index}`} fill={fill} stroke={stroke} />;
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  };

  const cardTitle = activeDataset === 'setup_tag' ? 'Analytics by Setup Tag' : 'Analytics by Key Indicators';
  const badgeText = `${sortedData.length} ${activeDataset === 'setup_tag' ? 'tags' : 'groups'}`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Local Controls Panel */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12,
        background: t.panel2,
        border: `1px solid ${t.border}`,
        borderRadius: 6,
        padding: '10px 16px'
      }}>
        {/* Selection toggles */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {/* Dataset select */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: t.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Dataset:</span>
            <select
              value={activeDataset}
              onChange={(e) => setActiveDataset(e.target.value)}
              style={{
                background: t.panel,
                border: `1px solid ${t.border}`,
                borderRadius: 4,
                color: t.text,
                fontFamily: t.ui,
                fontSize: 12.5,
                padding: '4px 8px',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="setup_tag">Setup tags</option>
              <option value="key_indicators_tags">Key indicators</option>
            </select>
          </div>

          {/* Metric select */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: t.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Metric:</span>
            <select
              value={selectedMetric}
              onChange={(e) => setSelectedMetric(e.target.value)}
              style={{
                background: t.panel,
                border: `1px solid ${t.border}`,
                borderRadius: 4,
                color: t.text,
                fontFamily: t.ui,
                fontSize: 12.5,
                padding: '4px 8px',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="total_pnl">Total P&L</option>
              <option value="total_trades">Trades</option>
              <option value="win_rate">Win Rate</option>
              <option value="profit_factor">Profit Factor</option>
            </select>
          </div>

          {/* Chart Type Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: t.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Chart:</span>
            <div style={{ display: 'inline-flex', borderRadius: 4, overflow: 'hidden', border: `1px solid ${t.border}` }}>
              {['bar', 'pie', 'line'].map(type => {
                const isActive = chartType === type;
                const isDisabled = type === 'line'; // Disabled categorical lines
                return (
                  <button
                    key={type}
                    type="button"
                    disabled={isDisabled}
                    onClick={() => setChartType(type)}
                    style={{
                      background: isActive ? t.panel3 : t.panel,
                      color: isDisabled ? t.dim : (isActive ? t.text : t.muted),
                      border: 'none',
                      padding: '4px 10px',
                      fontSize: 11.5,
                      fontFamily: t.ui,
                      fontWeight: 600,
                      cursor: isDisabled ? 'not-allowed' : 'pointer',
                      textTransform: 'capitalize'
                    }}
                    title={isDisabled ? "Line chart is disabled because tag categories are unordered variables." : ""}
                  >
                    {type}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Inputs / Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {/* Tag search input */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="text"
              placeholder="Search tag name..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{
                background: t.panel,
                border: `1px solid ${t.border}`,
                borderRadius: 4,
                color: t.text,
                fontFamily: t.ui,
                fontSize: 12,
                padding: '4px 8px',
                outline: 'none',
                width: 140
              }}
            />
          </div>

          {/* Min trades input */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, color: t.muted, fontFamily: t.ui }}>Min Trades:</span>
            <input
              type="number"
              placeholder="0"
              value={minTrades}
              onChange={(e) => setMinTrades(e.target.value)}
              style={{
                background: t.panel,
                border: `1px solid ${t.border}`,
                borderRadius: 4,
                color: t.text,
                fontFamily: t.mono,
                fontSize: 12,
                padding: '4px 8px',
                outline: 'none',
                width: 50
              }}
              min="0"
            />
          </div>

          {/* Clear filters button */}
          {(searchText || minTrades) && (
            <button
              onClick={() => {
                setSearchText('');
                setMinTrades('');
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: t.accent,
                fontSize: 11.5,
                fontFamily: t.ui,
                fontWeight: 600,
                cursor: 'pointer',
                padding: '4px 8px'
              }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Main Stats Card */}
      <div className="card" style={{ padding: 16 }}>
        <CardHeader eyebrow={cardTitle} badge={badgeText} />
        {sortedData.length === 0 ? (
          <div style={{ color: t.dim, textAlign: 'center', padding: '40px', fontFamily: t.mono, fontSize: 13 }}>
            No tag analytics match the current filters.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginTop: 16 }}>
            {/* Chart Column */}
            <div style={{ height: 280 }}>
              {renderChart()}
            </div>
            {/* Data Table Column */}
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', tableLayout: 'fixed', borderCollapse: 'collapse', fontSize: 12, fontFamily: t.mono }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${t.border}`, color: t.muted }}>
                    {renderHeader(activeDataset === 'setup_tag' ? 'Setup Tag' : 'Indicators', 'name', false)}
                    {renderHeader('Trades', 'total_trades', true)}
                    {renderHeader('Win Rate', 'win_rate', true)}
                    {renderHeader('PF', 'profit_factor', true)}
                    {renderHeader('Total P&L', 'total_pnl', true)}
                  </tr>
                </thead>
                <tbody>
                  {sortedData.map(row => (
                    <tr key={row.name} style={{ borderBottom: `1px solid ${t.border}` }}>
                      <td style={{
                        padding: '8px 12px',
                        textAlign: 'left',
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }} title={row.name}>
                        {formatTagLabel(row.name, false)}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.dim, fontVariantNumeric: 'tabular-nums' }}>
                        {row.total_trades}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.text, fontVariantNumeric: 'tabular-nums' }}>
                        {row.win_rate.toFixed(1)}%
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.text, fontVariantNumeric: 'tabular-nums' }}>
                        {row.profit_factor.toFixed(2)}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: row.total_pnl >= 0 ? t.bull : t.bear, fontVariantNumeric: 'tabular-nums' }}>
                        {row.total_pnl >= 0 ? `$${row.total_pnl.toFixed(2)}` : `-$${Math.abs(row.total_pnl).toFixed(2)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
