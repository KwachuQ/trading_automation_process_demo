// @vitest-environment happy-dom
/**
 * Unit tests for the useReview hook focusing on the loadTrades date-range fix.
 *
 * What is covered:
 *   1. Calling loadTrades({ dateFrom, dateTo }) hits the backend with
 *      date_from + date_to query params (range mode).
 *   2. Calling loadTrades({ sessionDate }) hits the backend with a single
 *      session_date query param (backwards-compatible single-day mode).
 *   3. Calling loadTrades() with no arguments sends no extra query params,
 *      letting the backend default to today.
 *   4. On a successful response, trades state is populated correctly.
 *   5. On a failed request, error state is set and trades remain empty.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mock the api module so no real HTTP calls are made.
// ---------------------------------------------------------------------------
vi.mock('../api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import api from '../api';
import { useReview } from './useReview';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal fake trade shape returned by the mocked backend. */
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
// Tests
// ---------------------------------------------------------------------------

describe('useReview — loadTrades', () => {
  beforeEach(() => {
    // Reset all mock state between tests
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls GET /review/trades with date_from and date_to when a date range is supplied', async () => {
    // Arrange: mock API returns two trades from different dates
    const fakeTrades = [
      makeTrade(1, '2026-06-01'),
      makeTrade(2, '2026-06-03'),
    ];
    api.get.mockResolvedValueOnce({ data: fakeTrades });

    const { result } = renderHook(() => useReview());

    // Act: call loadTrades with date range
    await act(async () => {
      await result.current.loadTrades({
        dateFrom: '2026-06-01',
        dateTo: '2026-06-07',
      });
    });

    // Assert: correct URL params were passed
    expect(api.get).toHaveBeenCalledOnce();
    const calledUrl = api.get.mock.calls[0][0];
    expect(calledUrl).toContain('date_from=2026-06-01');
    expect(calledUrl).toContain('date_to=2026-06-07');
    // session_date must NOT appear alongside a range request
    expect(calledUrl).not.toContain('session_date');

    // Assert: trades state is populated
    expect(result.current.trades).toHaveLength(2);
    expect(result.current.trades[0].session_date).toBe('2026-06-01');
    expect(result.current.trades[1].session_date).toBe('2026-06-03');
    expect(result.current.error).toBeNull();
  });

  it('calls GET /review/trades with session_date only when a single date is supplied', async () => {
    // Arrange
    const fakeTrades = [makeTrade(3, '2026-06-05')];
    api.get.mockResolvedValueOnce({ data: fakeTrades });

    const { result } = renderHook(() => useReview());

    // Act: backwards-compatible single-day mode
    await act(async () => {
      await result.current.loadTrades({ sessionDate: '2026-06-05' });
    });

    // Assert: only session_date in the query string
    const calledUrl = api.get.mock.calls[0][0];
    expect(calledUrl).toContain('session_date=2026-06-05');
    expect(calledUrl).not.toContain('date_from');
    expect(calledUrl).not.toContain('date_to');

    expect(result.current.trades).toHaveLength(1);
    expect(result.current.trades[0].id).toBe(3);
  });

  it('calls GET /review/trades with no extra params when called with no arguments', async () => {
    // Arrange: backend defaults to today — return empty list
    api.get.mockResolvedValueOnce({ data: [] });

    const { result } = renderHook(() => useReview());

    // Act: no arguments → backend decides the default date
    await act(async () => {
      await result.current.loadTrades();
    });

    // Assert: URL has no filter params (query string is empty or just '?')
    const calledUrl = api.get.mock.calls[0][0];
    // The URL will end with '?' or have no '?' at all — no meaningful params
    expect(calledUrl).not.toContain('date_from');
    expect(calledUrl).not.toContain('date_to');
    expect(calledUrl).not.toContain('session_date');

    expect(result.current.trades).toHaveLength(0);
  });

  it('does NOT include date_to when only dateFrom is provided (partial range is ignored)', async () => {
    // Supplying only one half of the range must not produce a malformed request.
    // The hook requires both dateFrom AND dateTo to activate range mode.
    api.get.mockResolvedValueOnce({ data: [] });

    const { result } = renderHook(() => useReview());

    await act(async () => {
      // Only dateFrom is set — dateTo is absent
      await result.current.loadTrades({ dateFrom: '2026-06-01' });
    });

    const calledUrl = api.get.mock.calls[0][0];
    // Range mode must NOT activate with only one bound
    expect(calledUrl).not.toContain('date_from');
    expect(calledUrl).not.toContain('date_to');
  });

  it('sets loading to true during the request and false after', async () => {
    // Arrange: delay the resolution to observe the in-flight state
    let resolveRequest;
    api.get.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRequest = () => resolve({ data: [] });
      })
    );

    const { result } = renderHook(() => useReview());

    // Kick off without awaiting so we can inspect mid-flight state
    act(() => {
      result.current.loadTrades({ dateFrom: '2026-06-01', dateTo: '2026-06-07' });
    });

    // Loading should now be true
    expect(result.current.loading).toBe(true);

    // Resolve the request and wait for state update
    await act(async () => {
      resolveRequest();
    });

    expect(result.current.loading).toBe(false);
  });

  it('sets error state and keeps trades empty when the API request fails', async () => {
    // Arrange: simulate a 500 backend error
    const fakeError = {
      response: { data: { detail: 'Internal server error' } },
    };
    api.get.mockRejectedValueOnce(fakeError);

    const { result } = renderHook(() => useReview());

    await act(async () => {
      await result.current.loadTrades({ dateFrom: '2026-06-01', dateTo: '2026-06-07' });
    });

    // Trades must remain empty; error must be set
    expect(result.current.trades).toHaveLength(0);
    expect(result.current.error).toBe('Internal server error');
    expect(result.current.loading).toBe(false);
  });
});

describe('useReview — bulkDeleteTrades', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends POST /review/trades/bulk-delete and updates trade list state on success', async () => {
    // Arrange
    const fakeTrades = [makeTrade(1, '2026-06-01'), makeTrade(2, '2026-06-01')];
    api.get.mockResolvedValueOnce({ data: fakeTrades });
    api.post.mockResolvedValueOnce({ data: { message: 'Deleted', trade_ids: [1] } });

    const { result } = renderHook(() => useReview());

    // Load initial trades
    await act(async () => {
      await result.current.loadTrades({ sessionDate: '2026-06-01' });
    });
    expect(result.current.trades).toHaveLength(2);

    // Act: bulk delete trade with ID 1
    await act(async () => {
      await result.current.bulkDeleteTrades([1]);
    });

    // Assert API call
    expect(api.post).toHaveBeenCalledWith('/review/trades/bulk-delete', { trade_ids: [1] });

    // Assert trade with ID 1 is removed, but trade with ID 2 remains
    expect(result.current.trades).toHaveLength(1);
    expect(result.current.trades[0].id).toBe(2);
  });

  it('sets error state when bulk delete API call fails', async () => {
    // Arrange
    api.post.mockRejectedValueOnce({
      response: { data: { detail: 'Delete failed' } }
    });

    const { result } = renderHook(() => useReview());

    await act(async () => {
      await expect(result.current.bulkDeleteTrades([1])).rejects.toThrow();
    });

    expect(result.current.error).toBe('Delete failed');
  });
});
