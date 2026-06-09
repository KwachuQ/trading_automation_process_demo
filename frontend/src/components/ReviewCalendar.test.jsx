// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import ReviewCalendar from './ReviewCalendar';

afterEach(() => {
  cleanup();
});

vi.mock('./ui', () => ({
  t: {
    bg: '#0c0d11',
    panel: '#13151c',
    panel2: '#181b24',
    border: 'rgba(255, 255, 255, 0.06)',
    text: '#e8edf5',
    muted: '#8a95a8',
    dim: '#505868',
    bull: '#00e676',
    bullSoft: 'rgba(0, 230, 118, 0.12)',
    bear: '#ff4455',
    bearSoft: 'rgba(255, 68, 85, 0.12)',
    mono: 'monospace',
    ui: 'sans-serif'
  },
  Btn: ({ children, onClick, ...props }) => <button onClick={onClick} {...props}>{children}</button>
}));

describe('ReviewCalendar', () => {
  const mockDailyPnl = [
    { Date: '2026-06-01', DailyPnL: 125.84, TradeCount: 3 },
    { Date: '2026-06-02', DailyPnL: -143.40, TradeCount: 2 }
  ];

  it('renders "No data" when daily_pnl is empty', () => {
    render(<ReviewCalendar dailyPnl={null} />);
    expect(screen.getByText(/No calendar data available/i)).toBeTruthy();
  });

  it('renders calendar grid and populates data for June 2026', () => {
    render(<ReviewCalendar dailyPnl={mockDailyPnl} initialDate="2026-06-01" />);
    
    // Check if the month is rendered
    expect(screen.getByText(/JUNE 2026/i)).toBeTruthy();

    // Check if the grid headers are there
    expect(screen.getByText('MO')).toBeTruthy();
    expect(screen.getByText('SU')).toBeTruthy();
    expect(screen.getByText('WEEKLY')).toBeTruthy();

    // Check the specific data points
    expect(screen.getByText('$125.84')).toBeTruthy();
    expect(screen.getByText('-$143.40')).toBeTruthy();
    expect(screen.getByText('3 trades')).toBeTruthy();
    expect(screen.getByText('2 trades')).toBeTruthy();
  });
});
