import React, { useState, useMemo } from 'react';
import { t, Btn } from './ui';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function ReviewCalendar({ dailyPnl, initialDate }) {
  const [currentMonth, setCurrentMonth] = useState(() => {
    return initialDate ? new Date(initialDate) : new Date();
  });

  if (!dailyPnl || dailyPnl.length === 0) {
    return (
      <div style={{ color: t.dim, textAlign: 'center', padding: '40px', fontFamily: t.mono, fontSize: 13 }}>
        No calendar data available for this range.
      </div>
    );
  }

  // Create a map for quick lookup: { "YYYY-MM-DD": { DailyPnL, TradeCount } }
  const dataMap = useMemo(() => {
    const map = {};
    dailyPnl.forEach(d => {
      map[d.Date] = d;
    });
    return map;
  }, [dailyPnl]);

  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();

  const firstDayOfMonth = new Date(year, month, 1);
  const lastDayOfMonth = new Date(year, month + 1, 0);

  // 0 = Sunday, ... 6 = Saturday
  const startDayOfWeek = firstDayOfMonth.getDay(); 
  const daysInMonth = lastDayOfMonth.getDate();

  const handlePrevMonth = () => setCurrentMonth(new Date(year, month - 1, 1));
  const handleNextMonth = () => setCurrentMonth(new Date(year, month + 1, 1));
  const handleToday = () => setCurrentMonth(new Date());

  const monthName = firstDayOfMonth.toLocaleString('en-US', { month: 'long', year: 'numeric' }).toUpperCase();

  // Calculate monthly sum
  let monthlyPnl = 0;

  // Group into weeks
  const weeks = [];
  let currentWeek = new Array(7).fill(null);

  for (let d = 1; d <= daysInMonth; d++) {
    const dayOfWeek = (startDayOfWeek + d - 1) % 7;
    currentWeek[dayOfWeek] = d;
    if (dayOfWeek === 6 || d === daysInMonth) {
      weeks.push(currentWeek);
      currentWeek = new Array(7).fill(null);
    }
  }

  // Generate grid cells
  const cells = [];
  weeks.forEach((week, weekIndex) => {
    let weeklyPnl = 0;
    let weeklyTrades = 0;

    week.forEach((d, dayIndex) => {
      if (d === null) {
        cells.push(<div key={`empty-${weekIndex}-${dayIndex}`} style={{ minHeight: '80px', padding: '8px', background: 'transparent' }} />);
        return;
      }

      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const dayData = dataMap[dateStr];

      if (dayData) {
        weeklyPnl += dayData.DailyPnL;
        weeklyTrades += dayData.TradeCount;
        monthlyPnl += dayData.DailyPnL;
      }

      const bgStyle = dayData
        ? dayData.DailyPnL > 0 ? 'rgba(0, 230, 118, 0.12)' : dayData.DailyPnL < 0 ? 'rgba(255, 68, 85, 0.12)' : t.panel
        : t.panel;

      cells.push(
        <div key={`day-${d}`} style={{ minHeight: '100px', padding: '8px', background: bgStyle, display: 'flex', flexDirection: 'column', gap: '4px', borderRadius: '4px' }}>
          <span style={{ fontFamily: t.ui, fontSize: '11px', fontWeight: 600, color: t.muted, alignSelf: 'flex-end' }}>{d}</span>
          {dayData && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', margin: 'auto 0', alignItems: 'center' }}>
              <span style={{ 
                fontFamily: t.ui, 
                fontSize: '14px', 
                fontWeight: 700, 
                color: dayData.DailyPnL >= 0 ? t.bull : t.bear 
              }}>
                {dayData.DailyPnL >= 0 ? '' : '-'}${Math.abs(dayData.DailyPnL).toFixed(2)}
              </span>
              <span style={{ fontFamily: t.ui, fontSize: '11px', color: t.muted }}>
                {dayData.TradeCount} {dayData.TradeCount === 1 ? 'trade' : 'trades'}
              </span>
            </div>
          )}
        </div>
      );
    });

    // Add weekly summary cell
    cells.push(
      <div key={`weekly-${weekIndex}`} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minHeight: '100px', padding: '8px', borderLeft: `1px solid ${t.border}`, background: weeklyPnl > 0 ?
        'rgba(0, 230, 118, 0.08)' : weeklyPnl < 0 ? 'rgba(255, 68, 85, 0.08)' : t.panel, borderRadius: '4px' }}>
        <span style={{ fontSize: '10px', fontWeight: 700, color: t.dim, marginBottom: '4px', letterSpacing: '0.05em' }}>WEEK {weekIndex + 1}</span>
        <span style={{ fontFamily: t.ui, fontSize: '14px', fontWeight: 700, color: weeklyPnl >= 0 ? t.bull : t.bear }}>
          {weeklyPnl >= 0 ? '' : '-'}${Math.abs(weeklyPnl).toFixed(2)}
        </span>
        <span style={{ fontFamily: t.ui, fontSize: '11px', color: t.muted, marginTop: '4px' }}>
          {weeklyTrades} {weeklyTrades === 1 ? 'trade' : 'trades'}
        </span>
      </div>
    );
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '24px', background: t.bg, borderRadius: '8px' }}>
      
      {/* Top Monthly Header */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: 700, color: t.muted, letterSpacing: '0.08em', textTransform: 'uppercase' }}>MONTHLY P/L</span>
        <span style={{ fontFamily: t.ui, fontSize: '20px', fontWeight: 700, color: monthlyPnl >= 0 ? t.bull : t.bear }}>
          {monthlyPnl >= 0 ? '' : '-'}${Math.abs(monthlyPnl).toFixed(2)}
        </span>
      </div>

      {/* Navigation Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <Btn onClick={handlePrevMonth} variant="ghost" style={{ padding: '4px 8px' }}><ChevronLeft size={16} /></Btn>
          <span style={{ fontSize: '15px', fontWeight: 700, color: t.text, fontFamily: t.ui, minWidth: '130px', textAlign: 'center' }}>
            {monthName}
          </span>
          <Btn onClick={handleNextMonth} variant="ghost" style={{ padding: '4px 8px' }}><ChevronRight size={16} /></Btn>
        </div>
        <Btn onClick={handleToday} variant="secondary" style={{ padding: '6px 16px', fontSize: '12px', fontWeight: 600 }}>TODAY</Btn>
      </div>

      {/* Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '6px' }}>
        {['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'WEEKLY'].map((day, idx) => (
          <div key={day} style={{ padding: '8px', textAlign: 'center', color: t.dim, fontSize: '12px', fontWeight: 700, fontFamily: t.ui, letterSpacing: '0.05em', borderBottom: idx === 7 ? 'none' : 'none' }}>
            {day}
          </div>
        ))}
        {cells}
      </div>

    </div>
  );
}
