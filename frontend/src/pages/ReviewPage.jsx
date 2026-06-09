import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useReview } from '../hooks/useReview';
import TradeTagGrid from '../components/TradeTagGrid';
import ReviewStatCards from '../components/ReviewStatCards';
import ReviewCharts from '../components/ReviewCharts';
import ReviewCalendar from '../components/ReviewCalendar';
import TagAnalytics from '../components/TagAnalytics';
import PlanVsExecution from '../components/PlanVsExecution';
import TagFilter from '../components/TagFilter';
import { useTradeStats } from '../hooks/useTradeStats';
import { t, CardHeader, Btn, InlineMsg } from '../components/ui';
import { GitMerge, RefreshCw, Trash2, Database, Eye, BarChart2, Filter } from 'lucide-react';

export default function ReviewPage() {
  const [sessionDate, setSessionDate] = useState(() => {
    // Default to today
    return new Date().toISOString().split('T')[0];
  });
  const [selectedTab, setSelectedTab] = useState('trades'); // 'trades', 'stats', 'analytics', 'plan'
  const [selectedTrades, setSelectedTrades] = useState(new Set());
  const [savingTradeId, setSavingTradeId] = useState(null);
  const [importing, setImporting] = useState(false);

  const [dateFrom, setDateFrom] = useState(() => {
    // Default to 30 days ago
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().split('T')[0];
  });
  const [dateTo, setDateTo] = useState(() => {
    // Default to today
    return new Date().toISOString().split('T')[0];
  });


  const [selectedTags, setSelectedTags] = useState([]);

  const {
    trades,
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
    loadStats
  } = useReview();

  // Compute all available tags
  const allTags = useMemo(() => {
    const tagSet = new Set();
    trades.forEach(trade => {
      if (trade.setup_tag) trade.setup_tag.split(',').forEach(tag => tagSet.add(tag.trim()));
      if (trade.additional_tag) trade.additional_tag.split(',').forEach(tag => tagSet.add(tag.trim()));
      if (trade.key_indicators_tags) trade.key_indicators_tags.split(',').forEach(tag => tagSet.add(tag.trim()));
      if (trade.scoring_criteria_tags) trade.scoring_criteria_tags.split(',').forEach(tag => tagSet.add(tag.trim()));
    });
    return Array.from(tagSet).filter(Boolean).sort();
  }, [trades]);

  // Filter trades using OR logic
  const filteredTrades = useMemo(() => {
    if (selectedTags.length === 0) return trades;
    return trades.filter(trade => {
      const tradeTags = new Set();
      if (trade.setup_tag) trade.setup_tag.split(',').forEach(tag => tradeTags.add(tag.trim()));
      if (trade.additional_tag) trade.additional_tag.split(',').forEach(tag => tradeTags.add(tag.trim()));
      if (trade.key_indicators_tags) trade.key_indicators_tags.split(',').forEach(tag => tradeTags.add(tag.trim()));
      if (trade.scoring_criteria_tags) trade.scoring_criteria_tags.split(',').forEach(tag => tradeTags.add(tag.trim()));
      return selectedTags.some(tag => tradeTags.has(tag));
    });
  }, [trades, selectedTags]);

  const localFilteredStats = useTradeStats(filteredTrades);

  // Load tag categories and initial trades on mount
  useEffect(() => {
    loadTagCategories();
  }, [loadTagCategories]);

  // Load trades whenever the date range changes
  useEffect(() => {
    loadTrades({ dateFrom, dateTo });
    setSelectedTrades(new Set());
    setImportStatus(null);
  }, [dateFrom, dateTo, loadTrades, setImportStatus]);

  // Load stats when stats tab is active or date range changes
  useEffect(() => {
    if (selectedTab === 'stats') {
      loadStats({ date_from: dateFrom, date_to: dateTo });
    }
  }, [selectedTab, dateFrom, dateTo, loadStats]);


  // Handle single trade tag/rating/comment updates
  const handleUpdateTrade = useCallback(async (tradeId, updates) => {
    setSavingTradeId(tradeId);
    try {
      await updateTrade(tradeId, updates);
    } catch (err) {
      console.error('Failed to update trade:', err);
    } finally {
      setSavingTradeId(null);
    }
  }, [updateTrade]);

  // Handle trade delete
  const handleDeleteTrade = useCallback(async (trade) => {
    const confirmed = window.confirm(
      `Delete trade #${trade.id} (${trade.symbol} ${trade.direction}, PnL: $${trade.pnl?.toFixed(2)})?\nThis action cannot be undone.`
    );
    if (!confirmed) return;

    try {
      await deleteTrade(trade.id);
      setSelectedTrades(prev => {
        const next = new Set(prev);
        next.delete(trade.id);
        return next;
      });
    } catch (err) {
      alert('Failed to delete trade: ' + err.message);
    }
  }, [deleteTrade]);

  // Handle trade merge
  const handleMergeTrades = useCallback(async () => {
    if (selectedTrades.size < 2) return;
    const tradeIds = Array.from(selectedTrades);
    
    const confirmed = window.confirm(`Are you sure you want to merge these ${tradeIds.length} trades into a single composite trade?`);
    if (!confirmed) return;

    try {
      const res = await mergeTrades(tradeIds);
      alert(res.message || 'Trades merged successfully.');
      setSelectedTrades(new Set());
      loadTrades({ dateFrom, dateTo }); // Reload with current range
    } catch (err) {
      alert('Failed to merge trades: ' + err.message);
    }
  }, [selectedTrades, mergeTrades, loadTrades, dateFrom, dateTo]);

  // Handle bulk delete trades
  const handleBulkDeleteTrades = useCallback(async () => {
    if (selectedTrades.size === 0) return;
    const tradeIds = Array.from(selectedTrades);
    
    const confirmed = window.confirm(
      `Delete ${tradeIds.length} selected trade(s)?\nThis action cannot be undone.`
    );
    if (!confirmed) return;

    try {
      const res = await bulkDeleteTrades(tradeIds);
      alert(res.message || 'Trades deleted successfully.');
      setSelectedTrades(new Set());
      // Reload trades and stats for the current range to keep them in sync
      loadTrades({ dateFrom, dateTo });
      loadStats({ date_from: dateFrom, date_to: dateTo });
    } catch (err) {
      alert('Failed to bulk delete trades: ' + err.message);
    }
  }, [selectedTrades, bulkDeleteTrades, loadTrades, loadStats, dateFrom, dateTo]);

  // Handle import trades from Sierra Chart
  const handleImportTrades = useCallback(async () => {
    setImporting(true);
    setImportStatus(null);
    try {
      const res = await importTrades();
      alert(`Import complete!\nImported: ${res.imported}\nSkipped (duplicates): ${res.skipped}\nTotal trades: ${res.total}`);
    } catch (err) {
      alert('Failed to import trades: ' + err.message);
    } finally {
      setImporting(false);
    }
  }, [importTrades, setImportStatus]);

  // Handle recalculating commissions
  const handleRecalculateCommissions = useCallback(async () => {
    const confirmed = window.confirm('Recalculate commissions for all trades in the database that currently show $0.00 fees?');
    if (!confirmed) return;

    try {
      const res = await recalculateCommissions();
      alert(res.message || `Commission recalculation completed.`);
      loadTrades({ dateFrom, dateTo }); // Reload with current range
    } catch (err) {
      alert('Failed to recalculate commissions: ' + err.message);
    }
  }, [recalculateCommissions, loadTrades, dateFrom, dateTo]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 48px)', padding: '14px 20px', gap: 14 }}>
      {/* Header toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: t.text }}>Post-Session Review</h1>
          <span
            style={{
              fontFamily: t.mono,
              fontSize: 11,
              color: t.muted,
              background: 'rgba(255, 255, 255, 0.04)',
              border: `1px solid ${t.border}`,
              borderRadius: 4,
              padding: '2px 8px'
            }}
          >
            {trades.length} Trades loaded
          </span>
        </div>

        {/* Date Range Selector and Main Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {/* From date */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: t.panel2, border: `1px solid ${t.border}`, borderRadius: 5, padding: '3px 8px' }}>
            <span style={{ fontSize: 11, color: t.dim, fontFamily: t.ui }}>From</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              style={{
                background: 'transparent',
                color: t.text,
                border: 'none',
                fontFamily: t.mono,
                fontSize: 12.5,
                outline: 'none',
                cursor: 'pointer'
              }}
            />
          </div>

          {/* To date */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: t.panel2, border: `1px solid ${t.border}`, borderRadius: 5, padding: '3px 8px' }}>
            <span style={{ fontSize: 11, color: t.dim, fontFamily: t.ui }}>To</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              style={{
                background: 'transparent',
                color: t.text,
                border: 'none',
                fontFamily: t.mono,
                fontSize: 12.5,
                outline: 'none',
                cursor: 'pointer'
              }}
            />
          </div>

          {/* Quick-select shortcuts */}
          {[
            { label: '1D', days: 1 },
            { label: '7D', days: 7 },
            { label: '30D', days: 30 },
          ].map(opt => (
            <button
              key={opt.label}
              onClick={() => {
                const today = new Date().toISOString().split('T')[0];
                const past = new Date(Date.now() - opt.days * 24 * 60 * 60 * 1000)
                  .toISOString().split('T')[0];
                setDateFrom(past);
                setDateTo(today);
              }}
              style={{
                background: 'rgba(255, 255, 255, 0.02)',
                border: `1px solid ${t.border}`,
                borderRadius: 4,
                color: t.muted,
                fontSize: 11,
                padding: '4px 8px',
                cursor: 'pointer',
                fontFamily: t.ui,
                transition: 'color 0.12s, background 0.12s'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = t.text; e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = t.muted; e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; }}
            >
              {opt.label}
            </button>
          ))}

          {/* Import Button */}
          <Btn onClick={handleImportTrades} disabled={importing || loading} loading={importing} variant="primary">
            {importing ? 'Importing' : 'Import Trades'}
          </Btn>

          {/* Recalculate Commissions */}
          <Btn onClick={handleRecalculateCommissions} disabled={loading} variant="secondary" title="Recalculate $0 fee commissions">
            <RefreshCw size={13} style={{ marginRight: 5, verticalAlign: 'middle' }} />
            Recalc Fees
          </Btn>
        </div>
      </div>

      {/* Info message displays */}
      <InlineMsg type="error" message={error} />
      {importStatus && (
        <InlineMsg
          type="success"
          message={`Successfully parsed and imported SC trade logs. Imported: ${importStatus.imported} new trades, skipped: ${importStatus.skipped} duplicates (Total in log: ${importStatus.total}).`}
        />
      )}

      {/* Main Review Tabs */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${t.border}`, gap: 2 }}>
        {[
          { id: 'trades', label: 'Trades Grid' },
          { id: 'stats', label: 'Stats & Charts' },
          { id: 'calendar', label: 'Calendar' },
          { id: 'analytics', label: 'Tag Analytics' },
          { id: 'plan', label: 'Plan vs Execution' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setSelectedTab(tab.id)}
            style={{
              background: 'transparent',
              border: 'none',
              color: selectedTab === tab.id ? t.text : t.muted,
              borderBottom: `2px solid ${selectedTab === tab.id ? t.bull : 'transparent'}`,
              fontFamily: t.ui,
              fontWeight: selectedTab === tab.id ? 600 : 500,
              fontSize: 13,
              padding: '8px 16px',
              cursor: 'pointer',
              transition: 'color 0.12s, border-color 0.12s'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Selection Action Bar (when multiple rows selected) */}
      {selectedTrades.size > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: t.bullSoft,
            border: `1px solid ${t.bullBorder}`,
            borderRadius: 6,
            padding: '10px 16px',
            color: t.bull
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <Database size={15} />
            <span style={{ fontFamily: t.mono, fontWeight: 700 }}>{selectedTrades.size}</span>
            <span>trades selected for batch actions</span>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            {selectedTrades.size >= 2 && (
              <Btn onClick={handleMergeTrades} variant="primary" style={{ padding: '4px 12px', fontSize: 12, background: 'rgba(0, 230, 118, 0.2)', border: `1px solid ${t.bull}` }}>
                <GitMerge size={13} style={{ marginRight: 5, verticalAlign: 'middle' }} />
                Merge Selected
              </Btn>
            )}
            <Btn
              onClick={handleBulkDeleteTrades}
              variant="secondary"
              style={{
                padding: '4px 12px',
                fontSize: 12,
                background: 'rgba(239, 83, 80, 0.15)',
                border: `1px solid ${t.bear}`,
                color: t.bear
              }}
            >
              <Trash2 size={13} style={{ marginRight: 5, verticalAlign: 'middle' }} />
              Delete Selected
            </Btn>
            <Btn
              onClick={() => setSelectedTrades(new Set())}
              variant="ghost"
              style={{ padding: '4px 12px', fontSize: 12, border: '1px solid rgba(0, 230, 118, 0.4)', color: t.bull }}
            >
              Clear Selection
            </Btn>
          </div>
        </div>
      )}

      {/* Tab Contents */}
      <div style={{ flex: 1, minHeight: 400 }}>
        {selectedTab === 'trades' && (
          <div style={{ display: 'grid', gridTemplateColumns: '250px 1fr', gap: 16 }}>
            {/* Left sidebar for Tag Filter */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <TagFilter
                allTags={allTags}
                selectedTags={selectedTags}
                onTagsChange={setSelectedTags}
              />
            </div>
            {/* Right main grid */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <CardHeader badge={loading ? 'running' : 'ready'} />
              <TradeTagGrid
                trades={filteredTrades}
                tagCategories={tagCategories}
                onUpdateTrade={handleUpdateTrade}
                onDeleteTrade={handleDeleteTrade}
                selectedTrades={selectedTrades}
                setSelectedTrades={setSelectedTrades}
                savingTradeId={savingTradeId}
              />
            </div>
          </div>
        )}

        {selectedTab === 'stats' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, width: '100%' }}>
            {/* Date range selector strip */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 12,
                background: t.panel2,
                border: `1px solid ${t.border}`,
                borderRadius: 6,
                padding: '10px 16px',
                width: '100%'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: t.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Filter Range:
                </span>
                
                {/* Date Inputs */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: t.panel, border: `1px solid ${t.border}`, borderRadius: 5, padding: '3px 8px' }}>
                  <span style={{ fontSize: 11, color: t.dim, fontFamily: t.ui }}>From</span>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    style={{
                      background: 'transparent',
                      color: t.text,
                      border: 'none',
                      fontFamily: t.mono,
                      fontSize: 12,
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: t.panel, border: `1px solid ${t.border}`, borderRadius: 5, padding: '3px 8px' }}>
                  <span style={{ fontSize: 11, color: t.dim, fontFamily: t.ui }}>To</span>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    style={{
                      background: 'transparent',
                      color: t.text,
                      border: 'none',
                      fontFamily: t.mono,
                      fontSize: 12,
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  />
                </div>
              </div>

              {/* Quick Selectors */}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {[
                  { label: 'Last 7D', days: 7 },
                  { label: 'Last 30D', days: 30 },
                  { label: 'Last 90D', days: 90 }
                ].map(opt => (
                  <button
                    key={opt.label}
                    onClick={() => {
                      const todayStr = new Date().toISOString().split('T')[0];
                      const past = new Date(Date.now() - opt.days * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
                      setDateFrom(past);
                      setDateTo(todayStr);
                    }}
                    style={{
                      background: 'rgba(255, 255, 255, 0.02)',
                      border: `1px solid ${t.border}`,
                      borderRadius: 4,
                      color: t.muted,
                      fontSize: 11,
                      padding: '4px 10px',
                      cursor: 'pointer',
                      fontFamily: t.ui,
                      transition: 'color 0.12s, background 0.12s, border-color 0.12s'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)';
                      e.currentTarget.style.color = t.text;
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)';
                      e.currentTarget.style.color = t.muted;
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
                
                <button
                  onClick={() => {
                    setDateFrom('');
                    setDateTo('');
                  }}
                  style={{
                    background: 'transparent',
                    border: '1px solid transparent',
                    borderRadius: 4,
                    color: t.dim,
                    fontSize: 11,
                    padding: '4px 8px',
                    cursor: 'pointer',
                    fontFamily: t.ui,
                    transition: 'color 0.12s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.color = t.text}
                  onMouseLeave={(e) => e.currentTarget.style.color = t.dim}
                >
                  All Time
                </button>
              </div>
            </div>

            {/* Loading or Dashboard stats */}
            {loading ? (
              <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 300 }}>
                <span style={{ fontFamily: t.mono, fontSize: 12.5, color: t.dim }} className="badge-running">
                  Computing statistics and chart metrics...
                </span>
              </div>
            ) : (
              <>
                <ReviewStatCards stats={stats?.stats} />
                <ReviewCharts charts={stats?.charts} />
              </>
            )}
          </div>
        )}

        {selectedTab === 'calendar' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, width: '100%' }}>
            {loading ? (
              <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 300 }}>
                <span style={{ fontFamily: t.mono, fontSize: 12.5, color: t.dim }} className="badge-running">
                  Loading calendar...
                </span>
              </div>
            ) : (
              <ReviewCalendar dailyPnl={stats?.charts?.daily_pnl} sessionDate={sessionDate} />
            )}
          </div>
        )}

        {selectedTab === 'analytics' && (
          <TagAnalytics dateFrom={dateFrom} dateTo={dateTo} />
        )}

        {selectedTab === 'plan' && (
          <PlanVsExecution sessionDate={sessionDate} />
        )}
      </div>

      {/* Footer helper */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11.5, color: t.dim, fontFamily: t.mono }}>
        <span>* Manual tagging dropdown updates and comment edits auto-saved immediately</span>
        <span>Auto-tagging matches closest live indicator snapshot</span>
      </div>
    </div>
  );
}
