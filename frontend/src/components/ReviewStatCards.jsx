import React from 'react';
import { t } from './ui';

export default function ReviewStatCards({ stats }) {
  if (!stats || !stats.summary) {
    return (
      <div style={{ color: t.dim, textAlign: 'center', padding: '40px', fontFamily: t.mono, fontSize: 13 }}>
        No statistics data available for this range.
      </div>
    );
  }

  const {
    total_pnl,
    gross_pnl,
    total_fees,
    win_rate,
    total_trades,
    profit_factor,
    expected_value,
    avg_win,
    avg_loss,
    best_trade,
    worst_trade
  } = stats.summary;

  const { best_day, worst_day } = stats.daily || {};
  const { avg_duration, avg_win_duration, avg_loss_duration } = stats.duration || {};

  const formatCurrency = (val) => {
    if (val === undefined || val === null) return '$0.00';
    const isNeg = val < 0;
    return `${isNeg ? '-' : ''}$${Math.abs(val).toFixed(2)}`;
  };

  const formatDuration = (val) => {
    if (val === undefined || val === null) return '0 s';
    const totalSeconds = Math.round(val);
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    if (m === 0) return `${s} s`;
    return `${m} min ${s} s`;
  };

  const getPnlColor = (val) => {
    if (val > 0) return t.bull;
    if (val < 0) return t.bear;
    return t.muted;
  };

  const getPnlBg = (val) => {
    if (val > 0) return t.bullSoft;
    if (val < 0) return t.bearSoft;
    return 'rgba(255, 255, 255, 0.01)';
  };

  const getPnlBorder = (val) => {
    if (val > 0) return t.bullBorder;
    if (val < 0) return t.bearBorder;
    return t.border;
  };

  const cards = [
    {
      label: 'Net P&L',
      value: formatCurrency(total_pnl),
      color: getPnlColor(total_pnl),
      bg: getPnlBg(total_pnl),
      border: getPnlBorder(total_pnl),
      subtitle: 'Net gains after commissions'
    },
    {
      label: 'Gross P&L',
      value: formatCurrency(gross_pnl),
      color: getPnlColor(gross_pnl),
      bg: getPnlBg(gross_pnl),
      border: getPnlBorder(gross_pnl),
      subtitle: 'Trading returns before fees'
    },
    {
      label: 'Total Fees',
      value: formatCurrency(total_fees),
      color: t.bear,
      bg: t.bearSoft,
      border: t.bearBorder,
      subtitle: `${total_trades > 0 ? formatCurrency(total_fees / total_trades) : '$0.00'} avg per trade`
    },
    {
      label: 'Win Rate',
      value: `${(win_rate || 0).toFixed(1)}%`,
      color: win_rate >= 50 ? t.bull : t.bear,
      bg: win_rate >= 50 ? t.bullSoft : t.bearSoft,
      border: win_rate >= 50 ? t.bullBorder : t.bearBorder,
      subtitle: `${total_trades} total F2F trades`
    },
    {
      label: 'Profit Factor',
      value: (profit_factor || 0).toFixed(2),
      color: profit_factor >= 1.5 ? t.bull : profit_factor >= 1.0 ? t.warning : t.bear,
      bg: profit_factor >= 1.5 ? t.bullSoft : profit_factor >= 1.0 ? 'rgba(245, 158, 11, 0.05)' : t.bearSoft,
      border: profit_factor >= 1.5 ? t.bullBorder : profit_factor >= 1.0 ? 'rgba(245, 158, 11, 0.2)' : t.bearBorder,
      subtitle: 'Gross wins / Gross losses'
    },
    {
      label: 'Expected Value',
      value: formatCurrency(expected_value),
      color: getPnlColor(expected_value),
      subtitle: 'Expectancy per trade'
    },
    {
      label: 'Avg Win',
      value: formatCurrency(avg_win),
      color: t.bull,
      subtitle: 'Average of winning trades'
    },
    {
      label: 'Avg Loss',
      value: formatCurrency(avg_loss),
      color: t.bear,
      subtitle: 'Average of losing trades'
    },
    {
      label: 'Best Trade',
      value: formatCurrency(best_trade),
      color: t.bull,
      subtitle: 'Peak net profit trade'
    },
    {
      label: 'Worst Trade',
      value: formatCurrency(worst_trade),
      color: t.bear,
      subtitle: 'Max net loss trade'
    },
    {
      label: 'Total Trades',
      value: total_trades || 0,
      color: t.text,
      subtitle: 'Executed trades count'
    },
    {
      label: 'Best Day',
      value: formatCurrency(best_day),
      color: t.bull,
      subtitle: 'Highest daily profit'
    },
    {
      label: 'Worst Day',
      value: formatCurrency(worst_day),
      color: t.bear,
      subtitle: 'Lowest daily profit'
    },
    {
      label: 'Avg Win Duration',
      value: formatDuration(avg_win_duration),
      color: t.bull,
      subtitle: 'Time in winning trades'
    },
    {
      label: 'Avg Loss Duration',
      value: formatDuration(avg_loss_duration),
      color: t.bear,
      subtitle: 'Time in losing trades'
    },
    {
      label: 'Avg Duration',
      value: formatDuration(avg_duration),
      color: t.text,
      subtitle: 'Overall time in trades'
    }
  ];

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
      gap: '12px',
      width: '100%'
    }}>
      {cards.map((c, idx) => (
        <div
          key={idx}
          className="card"
          style={{
            background: c.bg || t.panel,
            border: `1px solid ${c.border || t.border}`,
            padding: '16px',
            borderRadius: '8px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '8px',
            transition: 'transform 0.12s, border-color 0.12s'
          }}
        >
          <span style={{
            fontFamily: t.ui,
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: t.muted
          }}>
            {c.label}
          </span>
          <span style={{
            fontFamily: t.mono,
            fontSize: '20px',
            fontWeight: 700,
            color: c.color || t.text,
            letterSpacing: '-0.02em'
          }}>
            {c.value}
          </span>
          <span style={{
            fontFamily: t.ui,
            fontSize: '11px',
            color: t.dim,
            lineHeight: 1.2
          }}>
            {c.subtitle}
          </span>
        </div>
      ))}
    </div>
  );
}
