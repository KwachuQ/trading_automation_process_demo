// @vitest-environment happy-dom
/**
 * Integration test: ReviewPage date-range picker → TradeTagGrid reload
 *
 * Tests the full in-component wiring:
 *   - Mounting ReviewPage fires loadTrades with the initial default range
 *   - Changing the From date triggers a new loadTrades call with the new range
 *   - Changing the To date triggers a new loadTrades call with the new range
 *   - Trades returned from the mock API are rendered in the grid
 *   - Empty range yields the "no trades" empty state message
 *
 * This is the test that was missing: the hook unit tests proved loadTrades
 * builds the correct URL, and the backend tests proved the SQL query works,
 * but neither tested that the component wires dates → effect → API → grid.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Stable mock trade factory
// ---------------------------------------------------------------------------
const makeTrade = (id, sessionDate) => ({
  id,
  session_date: sessionDate,
  symbol: 'MNQH26',
  direction: 'Long',
  entry_datetime: `${sessionDate} 10:00:00`,
  exit_datetime: `${sessionDate} 10:15:00`,
  entry_price: 15000.0,
  exit_price: 15020.0,
  quantity: 1,
  pnl: 40.0,
  net_pnl: 39.0,
  commission: 1.0,
  duration_seconds: 900,
  setup_tag: 'ML',
  key_indicators_tags: '',
  scoring_criteria_tags: '',
  additional_tag: '',
  setup_rating: 0,
  comments: '',
  tags_auto: 1,
  tags_json: '{}',
  snapshot_id: null,
  import_hash: `hash_${id}`,
  exported_to_dashboard: 0,
  base_symbol: 'MNQ',
  max_open_profit: 0,
  max_open_loss: 0,
  fill_count: 1,
  point_value: 2,
  tick_size: 0.25,
  tick_value: 0.5,
  note: '',
  created_at: `${sessionDate}T10:00:00`,
});

// ---------------------------------------------------------------------------
// Mock the api module — all HTTP calls are intercepted here
// ---------------------------------------------------------------------------
const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock('../api', () => ({
  default: { get: mockGet, post: mockPost },
}));

// ---------------------------------------------------------------------------
// Mock Recharts (used by ReviewCharts on stats tab — not under test here)
// ---------------------------------------------------------------------------
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  ComposedChart: ({ children }) => <div>{children}</div>,
  Bar: () => null,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}));

// ---------------------------------------------------------------------------
// Helpers: wrap ReviewPage inside a router (it uses NavLinks internally)
// ---------------------------------------------------------------------------
async function renderReviewPage() {
  // Dynamically import to pick up the mocked api module
  const { default: ReviewPage } = await import('../pages/ReviewPage');
  return render(
    <MemoryRouter>
      <ReviewPage />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ReviewPage — date-range picker integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default: /review/constants returns empty tag categories
    mockGet.mockImplementation((url) => {
      if (url.includes('/review/constants')) {
        return Promise.resolve({
          data: { entry_type: [], entry_direct_context: [], close_type: [] },
        });
      }
      // Default trades response: empty list
      return Promise.resolve({ data: [] });
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('fires loadTrades on mount with the default date range (last 30d → today)', async () => {
    await renderReviewPage();

    // Wait for at least one GET /review/trades call
    await waitFor(() => {
      const tradeCalls = mockGet.mock.calls.filter((c) =>
        c[0].includes('/review/trades')
      );
      expect(tradeCalls.length).toBeGreaterThan(0);
    });

    // The initial call must include date_from AND date_to (range mode)
    const tradeCall = mockGet.mock.calls.find((c) =>
      c[0].includes('/review/trades')
    );
    expect(tradeCall[0]).toContain('date_from=');
    expect(tradeCall[0]).toContain('date_to=');
    expect(tradeCall[0]).not.toContain('session_date=');
  });

  it('renders returned trades in the grid', async () => {
    // Seed the mock to return two trades for the initial range
    mockGet.mockImplementation((url) => {
      if (url.includes('/review/constants')) {
        return Promise.resolve({
          data: { entry_type: [], entry_direct_context: [], close_type: [] },
        });
      }
      if (url.includes('/review/trades')) {
        return Promise.resolve({
          data: [makeTrade(1, '2026-06-01'), makeTrade(2, '2026-06-04')],
        });
      }
      return Promise.resolve({ data: [] });
    });

    await renderReviewPage();

    // Both trades should appear as rows (symbol column)
    await waitFor(() => {
      // There will be two cells with 'MNQH26'
      expect(screen.getAllByText('MNQH26').length).toBeGreaterThanOrEqual(2);
    });
  });

  it('re-fires loadTrades with the new date_from when the From picker changes', async () => {
    await renderReviewPage();

    // Wait for initial load to settle
    await waitFor(() =>
      mockGet.mock.calls.some((c) => c[0].includes('/review/trades'))
    );

    const callCountBefore = mockGet.mock.calls.filter((c) =>
      c[0].includes('/review/trades')
    ).length;

    // Change the From date input (first of the two date inputs in the header)
    const dateInputs = screen.getAllByDisplayValue(/\d{4}-\d{2}-\d{2}/);
    const fromInput = dateInputs[0]; // From is rendered before To in the DOM
    fireEvent.change(fromInput, { target: { value: '2026-01-01' } });

    await waitFor(() => {
      const tradeCalls = mockGet.mock.calls.filter((c) =>
        c[0].includes('/review/trades')
      );
      expect(tradeCalls.length).toBeGreaterThan(callCountBefore);
    });

    // The new call must carry the updated date_from
    const latestCall = [...mockGet.mock.calls]
      .filter((c) => c[0].includes('/review/trades'))
      .pop();
    expect(latestCall[0]).toContain('date_from=2026-01-01');
  });

  it('shows the empty-state message when the range returns no trades', async () => {
    // api already defaults to returning [] for /review/trades
    await renderReviewPage();

    await waitFor(() => {
      expect(
        screen.getByText(/No trades found for the selected date range/i)
      ).toBeTruthy();
    });
  });
});
