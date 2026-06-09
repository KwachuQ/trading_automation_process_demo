import { useState, useCallback } from 'react';
import api from '../api';

export function useReview() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tagCategories, setTagCategories] = useState({
    entry_type: [],
    entry_direct_context: [],
    close_type: []
  });
  const [importStatus, setImportStatus] = useState(null);
  const [stats, setStats] = useState(null);
  const [planVsExecution, setPlanVsExecution] = useState(null);

  // Load static tag categories for dropdowns
  const loadTagCategories = useCallback(async () => {
    try {
      const res = await api.get('/review/constants');
      setTagCategories(res.data);
    } catch (err) {
      console.error('Failed to load tag categories:', err);
    }
  }, []);

  // Load trades for a given session date or date range.
  // Accepts an options object: { sessionDate, dateFrom, dateTo }
  // When dateFrom + dateTo are both provided a range query is used;
  // otherwise falls back to single-day sessionDate lookup.
  const loadTrades = useCallback(async ({ sessionDate, dateFrom, dateTo } = {}) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (dateFrom && dateTo) {
        // Range mode — overrides single-day
        params.append('date_from', dateFrom);
        params.append('date_to', dateTo);
      } else if (sessionDate) {
        params.append('session_date', sessionDate);
      }
      const res = await api.get(`/review/trades?${params.toString()}`);
      setTrades(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch trades');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Import trades from Sierra Chart
  const importTrades = useCallback(async (filePath = null) => {
    setLoading(true);
    setError(null);
    setImportStatus(null);
    try {
      const url = filePath ? `/review/import?file_path=${encodeURIComponent(filePath)}` : '/review/import';
      const res = await api.post(url);
      setImportStatus({
        imported: res.data.imported,
        skipped: res.data.skipped,
        total: res.data.total
      });
      // Set returned trades
      setTrades(res.data.trades);
      return res.data;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to import trades');
      console.error(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Update a trade's tags/rating/comments
  const updateTrade = useCallback(async (tradeId, updates) => {
    setError(null);
    try {
      const res = await api.patch(`/review/trades/${tradeId}`, updates);
      setTrades(prev => prev.map(t => t.id === tradeId ? res.data : t));
      return res.data;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update trade');
      console.error(err);
      throw err;
    }
  }, []);

  // Delete a trade
  const deleteTrade = useCallback(async (tradeId) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.delete(`/review/trades/${tradeId}`);
      // Filter out deleted trade
      setTrades(prev => prev.filter(t => t.id !== tradeId));
      if (res.data.stats) {
        setStats(res.data.stats);
      }
      return res.data;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete trade');
      console.error(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Bulk delete trades
  const bulkDeleteTrades = useCallback(async (tradeIds) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post('/review/trades/bulk-delete', { trade_ids: tradeIds });
      const deletedIds = res.data.trade_ids || tradeIds;
      // Filter out deleted trades
      setTrades(prev => prev.filter(t => !deletedIds.includes(t.id)));
      return res.data;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to bulk delete trades');
      console.error(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Merge selected trades
  const mergeTrades = useCallback(async (tradeIds) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post('/review/trades/merge', { trade_ids: tradeIds });
      if (res.data.stats) {
        setStats(res.data.stats);
      }
      return res.data;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to merge trades');
      console.error(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Recalculate commissions for zero fee trades
  const recalculateCommissions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post('/review/recalculate-commissions');
      if (res.data.stats) {
        setStats(res.data.stats);
      }
      return res.data;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to recalculate commissions');
      console.error(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Load stats and charts
  const loadStats = useCallback(async (params = {}) => {
    setError(null);
    try {
      const queryParams = new URLSearchParams();
      if (params.session_date) queryParams.append('session_date', params.session_date);
      if (params.date_from) queryParams.append('date_from', params.date_from);
      if (params.date_to) queryParams.append('date_to', params.date_to);

      const res = await api.get(`/review/stats?${queryParams.toString()}`);
      setStats(res.data);
      return res.data;
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }, []);

  // Load stats by tag
  const loadStatsByTag = useCallback(async (tagColumn = 'setup_tag', params = {}) => {
    setError(null);
    try {
      const queryParams = new URLSearchParams();
      queryParams.append('tag_column', tagColumn);
      if (params.session_date) queryParams.append('session_date', params.session_date);
      if (params.date_from) queryParams.append('date_from', params.date_from);
      if (params.date_to) queryParams.append('date_to', params.date_to);

      const res = await api.get(`/review/stats-by-tag?${queryParams.toString()}`);
      return res.data;
    } catch (err) {
      console.error('Failed to load stats by tag:', err);
    }
  }, []);

  // Load Plan vs Execution
  const loadPlanVsExecution = useCallback(async (sessionDate) => {
    setError(null);
    try {
      const res = await api.get(`/review/plan-vs-execution?session_date=${sessionDate}`);
      setPlanVsExecution(res.data);
      return res.data;
    } catch (err) {
      console.error('Failed to load plan vs execution:', err);
    }
  }, []);

  return {
    trades,
    setTrades,
    loading,
    error,
    tagCategories,
    importStatus,
    setImportStatus,
    stats,
    planVsExecution,
    loadTagCategories,
    loadTrades,
    importTrades,
    updateTrade,
    deleteTrade,
    bulkDeleteTrades,
    mergeTrades,
    recalculateCommissions,
    loadStats,
    loadStatsByTag,
    loadPlanVsExecution
  };
}
