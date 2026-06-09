import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell
} from 'recharts';
import { t } from './ui';

export default function ReviewCharts({ charts }) {
  if (!charts) {
    return (
      <div style={{ color: t.dim, textAlign: 'center', padding: '40px', fontFamily: t.mono, fontSize: 13 }}>
        No chart data available.
      </div>
    );
  }

  const { daily_pnl = [], duration_distribution = [] } = charts;

  // Custom tooltips matching theme
  const formatCurrency = (val) => `$${Number(val).toFixed(2)}`;

  const CustomDailyTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          background: t.panel2,
          border: `1px solid ${t.border}`,
          borderRadius: '6px',
          padding: '10px 14px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)'
        }}>
          <p style={{ margin: '0 0 6px', fontSize: 12, fontWeight: 600, color: t.muted, fontFamily: t.mono }}>{label}</p>
          {payload.map((item, idx) => {
            const isPnl = item.dataKey === 'DailyPnL' || item.dataKey === 'CumulativePnL';
            const value = isPnl ? formatCurrency(item.value) : item.value;
            const color = item.value >= 0 ? t.bull : t.bear;
            const isCumulative = item.dataKey === 'CumulativePnL';

            return (
              <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', gap: 20, fontSize: 13, fontFamily: t.ui }}>
                <span style={{ color: t.muted }}>{item.name}:</span>
                <span style={{
                  fontFamily: t.mono,
                  fontWeight: 700,
                  color: isCumulative ? '#00e5ff' : color
                }}>
                  {value}
                </span>
              </div>
            );
          })}
        </div>
      );
    }
    return null;
  };

  const CustomDurationTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          background: t.panel2,
          border: `1px solid ${t.border}`,
          borderRadius: '6px',
          padding: '10px 14px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)'
        }}>
          <p style={{ margin: '0 0 6px', fontSize: 12, fontWeight: 600, color: t.muted }}>{label}</p>
          {payload.map((item, idx) => {
            const isWinRate = item.dataKey === 'win_rate';
            const value = isWinRate ? `${item.value.toFixed(1)}%` : `${item.value} trades`;
            const color = isWinRate ? '#ffd54f' : 'rgba(255, 255, 255, 0.7)';

            return (
              <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', gap: 20, fontSize: 13, fontFamily: t.ui }}>
                <span style={{ color: t.muted }}>{item.name}:</span>
                <span style={{ fontFamily: t.mono, fontWeight: 700, color }}>
                  {value}
                </span>
              </div>
            );
          })}
        </div>
      );
    }
    return null;
  };

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))',
      gap: '16px',
      width: '100%'
    }}>
      {/* 1. Daily PnL and Cumulative PnL */}
      <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: t.muted, margin: 0 }}>
            Daily P&L & Cumulative P&L
          </h2>
          <span style={{ fontFamily: t.mono, fontSize: 11, color: t.dim }}>
            {daily_pnl.length} Trading Days
          </span>
        </div>

        <div style={{ width: '100%', height: 320 }}>
          {daily_pnl.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: t.dim, fontFamily: t.mono, fontSize: 12 }}>
              No daily trade data available for this range
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={daily_pnl} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255, 255, 255, 0.03)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="Date"
                  stroke={t.dim}
                  tick={{ fill: t.muted, fontSize: 10.5, fontFamily: t.mono }}
                  axisLine={{ stroke: t.border }}
                  tickLine={{ stroke: t.border }}
                />
                <YAxis
                  stroke={t.dim}
                  tick={{ fill: t.muted, fontSize: 10.5, fontFamily: t.mono }}
                  axisLine={{ stroke: t.border }}
                  tickLine={{ stroke: t.border }}
                  tickFormatter={(val) => `$${val}`}
                />
                <Tooltip content={<CustomDailyTooltip />} cursor={{ fill: 'rgba(255, 255, 255, 0.02)' }} />
                <Legend
                  verticalAlign="top"
                  height={36}
                  wrapperStyle={{ fontSize: 12, fontFamily: t.ui }}
                />
                <Bar dataKey="DailyPnL" name="Daily Net P&L">
                  {daily_pnl.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.DailyPnL >= 0 ? t.bullSoft : t.bearSoft}
                      stroke={entry.DailyPnL >= 0 ? t.bullBorder : t.bearBorder}
                      strokeWidth={1}
                    />
                  ))}
                </Bar>
                <Line
                  type="monotone"
                  dataKey="CumulativePnL"
                  name="Cumulative Net P&L"
                  stroke="#00e5ff"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#00e5ff', strokeWidth: 1 }}
                  activeDot={{ r: 5, fill: '#ffffff', stroke: '#00e5ff', strokeWidth: 2 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* 2. Duration Distribution & Win Rate */}
      <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: t.muted, margin: 0 }}>
            Duration Distribution & Win Rate
          </h2>
          <span style={{ fontFamily: t.mono, fontSize: 11, color: t.dim }}>
            By Time Buckets
          </span>
        </div>

        <div style={{ width: '100%', height: 320 }}>
          {duration_distribution.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: t.dim, fontFamily: t.mono, fontSize: 12 }}>
              No duration distribution data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={duration_distribution} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255, 255, 255, 0.03)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="range"
                  stroke={t.dim}
                  tick={{ fill: t.muted, fontSize: 10, fontFamily: t.ui }}
                  axisLine={{ stroke: t.border }}
                  tickLine={{ stroke: t.border }}
                />
                <YAxis
                  yAxisId="left"
                  stroke={t.dim}
                  tick={{ fill: t.muted, fontSize: 10.5, fontFamily: t.mono }}
                  axisLine={{ stroke: t.border }}
                  tickLine={{ stroke: t.border }}
                  allowDecimals={false}
                  label={{ value: 'Trades Count', angle: -90, position: 'insideLeft', offset: -2, style: { fill: t.muted, fontSize: 11, fontFamily: t.ui } }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke={t.dim}
                  tick={{ fill: t.muted, fontSize: 10.5, fontFamily: t.mono }}
                  axisLine={{ stroke: t.border }}
                  tickLine={{ stroke: t.border }}
                  domain={[0, 100]}
                  tickFormatter={(val) => `${val}%`}
                  label={{ value: 'Win Rate', angle: 90, position: 'insideRight', offset: 2, style: { fill: t.muted, fontSize: 11, fontFamily: t.ui } }}
                />
                <Tooltip content={<CustomDurationTooltip />} cursor={{ fill: 'rgba(255, 255, 255, 0.02)' }} />
                <Legend
                  verticalAlign="top"
                  height={36}
                  wrapperStyle={{ fontSize: 12, fontFamily: t.ui }}
                />
                <Bar
                  yAxisId="left"
                  dataKey="count"
                  name="Trades Count"
                  fill="rgba(255, 255, 255, 0.08)"
                  stroke="rgba(255, 255, 255, 0.2)"
                  strokeWidth={1}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="win_rate"
                  name="Win Rate"
                  stroke="#ffd54f"
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#ffd54f', strokeWidth: 1 }}
                  activeDot={{ r: 5, fill: '#ffffff', stroke: '#ffd54f', strokeWidth: 2 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
