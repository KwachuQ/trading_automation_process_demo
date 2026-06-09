// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import ReviewStatCards from './ReviewStatCards';
import ReviewCharts from './ReviewCharts';

// Automatically clean up JSDOM/HappyDOM tree after each test
afterEach(() => {
  cleanup();
});

// Mock Recharts to avoid layout/ResizeObserver errors in testing environments
vi.mock('recharts', () => {
  return {
    ResponsiveContainer: ({ children }) => <div data-testid="mock-responsive-container">{children}</div>,
    ComposedChart: ({ children, data }) => (
      <div data-testid="mock-composed-chart" data-count={data ? data.length : 0}>
        {children}
      </div>
    ),
    BarChart: ({ children, data }) => (
      <div data-testid="mock-bar-chart" data-count={data ? data.length : 0}>
        {children}
      </div>
    ),
    PieChart: ({ children }) => <div data-testid="mock-pie-chart">{children}</div>,
    Pie: ({ data, nameKey }) => (
      <div data-testid="mock-pie" data-count={data ? data.length : 0} data-namekey={nameKey}>
        {data?.map((d, i) => <span key={i} data-name={d.name} data-val={d.value} />)}
      </div>
    ),
    Bar: ({ name }) => <div data-testid="mock-bar">{name}</div>,
    Line: ({ name }) => <div data-testid="mock-line">{name}</div>,
    XAxis: () => <div data-testid="mock-xaxis" />,
    YAxis: () => <div data-testid="mock-yaxis" />,
    CartesianGrid: () => <div data-testid="mock-grid" />,
    Tooltip: () => <div data-testid="mock-tooltip" />,
    Legend: () => <div data-testid="mock-legend" />,
    Cell: () => <div data-testid="mock-cell" />
  };
});

// Mock UI helper styles to avoid missing CSS variables in tests
vi.mock('./ui', () => ({
  t: {
    bg: '#0c0d11',
    panel: '#13151c',
    panel2: '#181b24',
    panel3: '#1e2230',
    border: 'rgba(255, 255, 255, 0.06)',
    text: '#e8edf5',
    muted: '#8a95a8',
    dim: '#505868',
    bull: '#00e676',
    bullSoft: 'rgba(0, 230, 118, 0.12)',
    bullBorder: 'rgba(0, 230, 118, 0.28)',
    bear: '#ff4455',
    bearSoft: 'rgba(255, 68, 85, 0.12)',
    bearBorder: 'rgba(255, 68, 85, 0.28)',
    warning: '#f59e0b',
    mono: 'monospace',
    ui: 'sans-serif'
  },
  CardHeader: ({ eyebrow, badge }) => (
    <div data-testid="mock-card-header">
      <span>{eyebrow}</span>
      {badge && <span>{badge}</span>}
    </div>
  )
}));

describe('ReviewStatCards', () => {
  const mockStats = {
    summary: {
      total_pnl: 250.50,
      gross_pnl: 275.00,
      total_fees: 24.50,
      win_rate: 66.67,
      total_trades: 3,
      profit_factor: 2.50,
      expected_value: 83.50,
      avg_win: 137.50,
      avg_loss: -50.00,
      best_trade: 200.00,
      worst_trade: -65.00 // Changed to be unique from other values
    },
    duration: {
      avg_duration: 104.00,
      avg_win_duration: 160.00,
      avg_loss_duration: 20.00
    },
    daily: {
      best_day: 125.84,
      worst_day: -143.40
    }
  };

  it('renders "No statistics data" when stats are empty', () => {
    render(<ReviewStatCards stats={null} />);
    expect(screen.getByText(/No statistics data available/i)).toBeTruthy();
  });

  it('renders all 16 trading performance metric cards with values', () => {
    render(<ReviewStatCards stats={mockStats} />);

    // Check headings (using case-insensitive queries since text-transform doesn't change DOM content)
    expect(screen.getByText(/Net P&L/i)).toBeTruthy();
    expect(screen.getByText(/Gross P&L/i)).toBeTruthy();
    expect(screen.getByText(/Total Fees/i)).toBeTruthy();
    expect(screen.getByText(/Win Rate/i)).toBeTruthy();
    expect(screen.getByText(/Profit Factor/i)).toBeTruthy();
    expect(screen.getByText(/Expected Value/i)).toBeTruthy();
    expect(screen.getByText('Avg Win')).toBeTruthy();
    expect(screen.getByText('Avg Loss')).toBeTruthy();
    expect(screen.getByText('Best Trade')).toBeTruthy();
    expect(screen.getByText('Worst Trade')).toBeTruthy();
    expect(screen.getByText(/Total Trades/i)).toBeTruthy();
    expect(screen.getByText(/Best Day/i)).toBeTruthy();
    expect(screen.getByText(/Worst Day/i)).toBeTruthy();
    expect(screen.getByText(/Avg Win Duration/i)).toBeTruthy();
    expect(screen.getByText(/Avg Loss Duration/i)).toBeTruthy();
    expect(screen.getByText(/Avg Duration/i)).toBeTruthy();

    // Check formatted values
    expect(screen.getByText('$250.50')).toBeTruthy();
    expect(screen.getByText('$275.00')).toBeTruthy();
    expect(screen.getByText('$24.50')).toBeTruthy();
    expect(screen.getByText('66.7%')).toBeTruthy();
    expect(screen.getByText('2.50')).toBeTruthy();
    expect(screen.getByText('$83.50')).toBeTruthy();
    expect(screen.getByText('$137.50')).toBeTruthy();
    expect(screen.getByText('-$50.00')).toBeTruthy();
    expect(screen.getByText('$200.00')).toBeTruthy();
    expect(screen.getByText('-$65.00')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
    expect(screen.getByText('$125.84')).toBeTruthy();
    expect(screen.getByText('-$143.40')).toBeTruthy();
    expect(screen.getByText('2 min 40 s')).toBeTruthy();
    expect(screen.getByText('20 s')).toBeTruthy();
    expect(screen.getByText('1 min 44 s')).toBeTruthy();
  });

  it('handles negative stats with correct colors and formatting', () => {
    const negativeStats = {
      summary: {
        total_pnl: -120.00,
        gross_pnl: -100.00,
        total_fees: 20.00,
        win_rate: 33.33,
        total_trades: 3,
        profit_factor: 0.50,
        expected_value: -40.00,
        avg_win: 80.00,
        avg_loss: -110.00,
        best_trade: 80.00,
        worst_trade: -130.00 // All values unique to prevent getByText throwing on duplicate matches
      }
    };
    const negativeDurationStats = {
        summary: negativeStats.summary,
        duration: { avg_duration: 0.0, avg_win_duration: 0.0, avg_loss_duration: 0.0 },
        daily: { best_day: -10.0, worst_day: -50.0 }
    };

    render(<ReviewStatCards stats={negativeDurationStats} />);
    expect(screen.getByText('-$120.00')).toBeTruthy();
    expect(screen.getByText('-$100.00')).toBeTruthy();
    expect(screen.getByText('-$40.00')).toBeTruthy();
    expect(screen.getByText('-$130.00')).toBeTruthy();
  });
});

describe('ReviewCharts', () => {
  const mockCharts = {
    daily_pnl: [
      { Date: '2026-05-29', DailyPnL: 100, CumulativePnL: 100 },
      { Date: '2026-06-01', DailyPnL: 150, CumulativePnL: 250 }
    ],
    duration_distribution: [
      { range: '15-45 sec', count: 3, win_rate: 66.7 },
      { range: '1 min - 2 min', count: 1, win_rate: 100 }
    ]
  };

  it('renders "No chart data" when charts are empty', () => {
    render(<ReviewCharts charts={null} />);
    expect(screen.getByText(/No chart data available/i)).toBeTruthy();
  });

  it('renders both daily P&L and duration distribution charts', () => {
    render(<ReviewCharts charts={mockCharts} />);

    // Check headers using case-insensitive matches to align with raw text in DOM
    expect(screen.getByText(/Daily P&L & Cumulative P&L/i)).toBeTruthy();
    expect(screen.getByText(/Duration Distribution & Win Rate/i)).toBeTruthy();

    // Check that ComposedCharts rendered with correct items count
    const charts = screen.getAllByTestId('mock-composed-chart');
    expect(charts).toHaveLength(2);
    expect(charts[0].getAttribute('data-count')).toBe('2'); // daily_pnl rows count
    expect(charts[1].getAttribute('data-count')).toBe('2'); // duration rows count
  });
});

import TagFilter from './TagFilter';
import { fireEvent } from '@testing-library/react';

describe('TagFilter', () => {
  const mockTags = ['ML', 'MS', 'MRL', 'MRS'];
  
  it('renders all tags and handles selection', () => {
    const onTagsChange = vi.fn();
    render(<TagFilter allTags={mockTags} selectedTags={[]} onTagsChange={onTagsChange} />);
    
    expect(screen.getByText('ML')).toBeTruthy();
    expect(screen.getByText('MS')).toBeTruthy();
    
    fireEvent.click(screen.getByText('ML').closest('button'));
    expect(onTagsChange).toHaveBeenCalledWith(['ML']);
  });

  it('filters tags by search query', () => {
    const onTagsChange = vi.fn();
    render(<TagFilter allTags={mockTags} selectedTags={[]} onTagsChange={onTagsChange} />);
    
    const input = screen.getByPlaceholderText('Search tags...');
    fireEvent.change(input, { target: { value: 'm' } });
    
    expect(screen.getByText('ML')).toBeTruthy();
    expect(screen.getByText('MS')).toBeTruthy();
    expect(screen.getByText('MRL')).toBeTruthy();
  });
});

import PlanVsExecution from './PlanVsExecution';

// Mock useReview hook for PlanVsExecution and TagAnalytics
const mockLoadStatsByTag = vi.fn().mockImplementation((category) => {
  if (category === 'setup_tag') {
    return Promise.resolve({
      'Breakout': { summary: { total_pnl: 150.0, win_rate: 60.0, total_trades: 5, profit_factor: 1.8 } },
      'Pullback': { summary: { total_pnl: -50.0, win_rate: 40.0, total_trades: 10, profit_factor: 0.8 } }
    });
  }
  if (category === 'key_indicators_tags') {
    return Promise.resolve({
      'RSI, MACD': { summary: { total_pnl: 200.0, win_rate: 70.0, total_trades: 8, profit_factor: 2.2 } }
    });
  }
  return Promise.resolve({});
});

vi.mock('../hooks/useReview', () => ({
  useReview: () => ({
    loadPlanVsExecution: vi.fn().mockResolvedValue({
      summary: { total_trades: 3, aligned_count: 2, unaligned_count: 1, unplanned_count: 0 },
      scenarios: [
        { setup_type: 'ML', rationale: 'Test Rationale', targets: 'Test Targets', aligned_trades: [], unaligned_trades: [] }
      ],
      unplanned_trades: []
    }),
    loadStatsByTag: mockLoadStatsByTag
  })
}));

describe('PlanVsExecution', () => {
  it('renders summary and scenarios', async () => {
    render(<PlanVsExecution sessionDate="2026-06-01" />);
    expect(screen.getByText(/Loading Plan vs Execution/i)).toBeTruthy();
    
    const summary = await screen.findByText('Plan Adherence');
    expect(summary).toBeTruthy();
    
    expect(screen.getByText(/ML/i)).toBeTruthy();
    expect(screen.getByText(/Test Rationale/i)).toBeTruthy();
  });
});

import TagAnalytics from './TagAnalytics';

describe('TagAnalytics', () => {
  it('renders loading initially and then loads/displays setup tags by default', async () => {
    render(<TagAnalytics dateFrom="2026-05-01" dateTo="2026-06-01" />);
    
    // Check loading indicator
    expect(screen.getByText(/Computing tag analytics/i)).toBeTruthy();
    
    // Wait for the data to load and render
    const cardTitle = await screen.findByText('Analytics by Setup Tag');
    expect(cardTitle).toBeTruthy();
    
    // Check table headers and data rows
    expect(screen.getByText('Breakout')).toBeTruthy();
    expect(screen.getByText('Pullback')).toBeTruthy();
    expect(screen.getByText('$150.00')).toBeTruthy();
    expect(screen.getByText('-$50.00')).toBeTruthy();
  });

  it('allows dataset switching and local tag filtering', async () => {
    render(<TagAnalytics dateFrom="2026-05-01" dateTo="2026-06-01" />);
    
    // Wait for load
    await screen.findByText('Analytics by Setup Tag');
    
    // Switch to Key Indicators dataset
    const datasetSelect = screen.getByDisplayValue('Setup tags');
    fireEvent.change(datasetSelect, { target: { value: 'key_indicators_tags' } });
    
    // Verify dataset switched
    expect(await screen.findByText('Analytics by Key Indicators')).toBeTruthy();
    // Key indicator should be grouped and formatted with bullet separator
    expect(screen.getByText('RSI • MACD')).toBeTruthy();
    expect(screen.getByText('$200.00')).toBeTruthy();
    
    // Switch back to setup tags
    fireEvent.change(datasetSelect, { target: { value: 'setup_tag' } });
    expect(await screen.findByText('Analytics by Setup Tag')).toBeTruthy();
    
    // Filter tags by search text
    const searchInput = screen.getByPlaceholderText('Search tag name...');
    fireEvent.change(searchInput, { target: { value: 'break' } });
    
    // Only "Breakout" should remain, "Pullback" should be gone
    expect(screen.getByText('Breakout')).toBeTruthy();
    expect(screen.queryByText('Pullback')).toBeNull();
    
    // Clear filters
    const clearBtn = screen.getByText('Clear');
    fireEvent.click(clearBtn);
    expect(screen.getByText('Pullback')).toBeTruthy();
  });
});
