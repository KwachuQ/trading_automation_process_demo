import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { ArrowUp, ArrowDown, Trash2, HelpCircle, Loader2 } from 'lucide-react';
import { t, Btn } from './ui';

export default function TradeTagGrid({
  trades = [],
  tagCategories = {},
  onUpdateTrade = () => {},
  onDeleteTrade = () => {},
  selectedTrades = new Set(),
  setSelectedTrades = () => {},
  savingTradeId = null
}) {
  // Sort state
  const [sortConfig, setSortConfig] = useState({ key: 'entry_datetime', direction: 'desc' });

  // Local input state for comments to prevent cursor jumping or typing lag
  const [localComments, setLocalComments] = useState({});

  // Sync local comments input when trades data changes
  useEffect(() => {
    const comments = {};
    trades.forEach(trade => {
      comments[trade.id] = trade.comments || '';
    });
    setLocalComments(comments);
  }, [trades]);

  // Extract separate tags from the comma-separated `additional_tag` field
  const getParsedManualTags = useCallback((additionalTagStr) => {
    if (!additionalTagStr) return { entryType: '', entryContext: '', closeType: '' };
    const tags = additionalTagStr.split(',').map(s => s.trim());
    
    const entryType = tags.find(tag => tagCategories.entry_type?.includes(tag)) || '';
    const entryContext = tags.find(tag => tagCategories.entry_direct_context?.includes(tag)) || '';
    const closeType = tags.find(tag => tagCategories.close_type?.includes(tag)) || '';

    return { entryType, entryContext, closeType };
  }, [tagCategories]);

  // Handle updates to manual tags via individual dropdown changes
  const handleManualTagChange = useCallback((trade, categoryKey, selectedValue) => {
    const { entryType, entryContext, closeType } = getParsedManualTags(trade.additional_tag);
    
    let nextEntryType = entryType;
    let nextEntryContext = entryContext;
    let nextCloseType = closeType;

    if (categoryKey === 'entry_type') nextEntryType = selectedValue;
    if (categoryKey === 'entry_direct_context') nextEntryContext = selectedValue;
    if (categoryKey === 'close_type') nextCloseType = selectedValue;

    const newAdditionalTags = [nextEntryType, nextEntryContext, nextCloseType]
      .filter(Boolean)
      .join(', ');

    onUpdateTrade(trade.id, { additional_tag: newAdditionalTags });
  }, [getParsedManualTags, onUpdateTrade]);

  // Sorting logic
  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const sortedTrades = useMemo(() => {
    let sortable = [...trades];
    if (sortConfig.key) {
      sortable.sort((a, b) => {
        let aVal = a[sortConfig.key];
        let bVal = b[sortConfig.key];

        if (['pnl', 'net_pnl', 'entry_price', 'exit_price', 'duration_seconds', 'quantity', 'commission', 'setup_rating'].includes(sortConfig.key)) {
          aVal = parseFloat(aVal) || 0;
          bVal = parseFloat(bVal) || 0;
        }

        if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return sortable;
  }, [trades, sortConfig]);

  // Row selection helpers
  const toggleRow = (tradeId) => {
    const next = new Set(selectedTrades);
    if (next.has(tradeId)) next.delete(tradeId);
    else next.add(tradeId);
    setSelectedTrades(next);
  };

  const toggleAll = () => {
    if (selectedTrades.size === trades.length) {
      setSelectedTrades(new Set());
    } else {
      setSelectedTrades(new Set(trades.map(t => t.id)));
    }
  };

  // Format helper for duration
  const formatDuration = (seconds) => {
    if (!seconds) return '0s';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.round(seconds % 60);
    if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  // Helper to parse key indicators tags (format: key:value)
  const renderKeyIndicators = (indicatorStr) => {
    if (!indicatorStr) return <span style={{ color: t.dim }}>-</span>;
    const items = indicatorStr.split(',').map(s => s.trim());
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {items.map(item => {
          const [key, val] = item.split(':');
          return (
            <span
              key={item}
              style={{
                fontFamily: t.mono,
                fontSize: 9,
                fontWeight: 600,
                color: t.muted,
                background: 'rgba(255, 255, 255, 0.04)',
                border: `1px solid ${t.border}`,
                borderRadius: 4,
                padding: '1px 5px'
              }}
            >
              <span style={{ color: t.dim }}>{key}:</span>
              <span style={{ color: t.text, marginLeft: 2 }}>{val}</span>
            </span>
          );
        })}
      </div>
    );
  };

  // Helper to render scoring criteria
  const renderCriteria = (criteriaStr) => {
    if (!criteriaStr) return <span style={{ color: t.dim }}>-</span>;
    const items = criteriaStr.split(',').map(s => s.trim());
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {items.map(item => (
          <span
            key={item}
            style={{
              fontFamily: t.mono,
              fontSize: 9,
              fontWeight: 500,
              color: t.accent,
              background: 'rgba(255, 255, 255, 0.06)',
              border: `1px solid ${t.border}`,
              borderRadius: 4,
              padding: '1px 5px'
            }}
          >
            {item}
          </span>
        ))}
      </div>
    );
  };

  return (
    <div style={{ overflowX: 'auto', background: t.panel, border: `1px solid ${t.border}`, borderRadius: 8 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: 1200 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${t.border}`, background: 'rgba(255,255,255,0.02)' }}>
            {/* Checkbox Header */}
            <th style={{ padding: '12px 16px', width: 48 }}>
              <input
                type="checkbox"
                checked={trades.length > 0 && selectedTrades.size === trades.length}
                onChange={toggleAll}
                style={{ cursor: 'pointer', accentColor: t.accent }}
              />
            </th>
            {/* Headers with Sorting */}
            {[
              { key: 'entry_datetime', label: 'Time' },
              { key: 'symbol', label: 'Symbol' },
              { key: 'direction', label: 'Dir' },
              { key: 'quantity', label: 'Size' },
              { key: 'entry_price', label: 'Prices' },
              { key: 'pnl', label: 'Gross PnL' },
              { key: 'net_pnl', label: 'Net PnL' },
              { key: 'commission', label: 'Fees' },
              { key: 'duration_seconds', label: 'Duration' },
              { key: 'setup_tag', label: 'Setup Tag' },
              { key: 'key_indicators_tags', label: 'Key Indicators' },
              { key: 'scoring_criteria_tags', label: 'Scoring Criteria' },
              { key: 'additional_tag', label: 'Manual Tags' },
              { key: 'setup_rating', label: 'Rating' },
              { key: 'comments', label: 'Comments' }
            ].map(col => (
              <th
                key={col.key}
                onClick={() => handleSort(col.key)}
                style={{
                  padding: '12px 10px',
                  fontFamily: t.mono,
                  fontSize: 10,
                  fontWeight: 700,
                  color: t.muted,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                  userSelect: 'none'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  {col.label}
                  {sortConfig.key === col.key && (
                    sortConfig.direction === 'asc' ? <ArrowUp size={12} style={{ color: t.success }} /> : <ArrowDown size={12} style={{ color: t.success }} />
                  )}
                </div>
              </th>
            ))}
            {/* Actions Header */}
            <th style={{ padding: '12px 16px', width: 60, textAlign: 'center', fontFamily: t.mono, fontSize: 10, fontWeight: 700, color: t.muted }}>
              DEL
            </th>
          </tr>
        </thead>
        <tbody style={{ fontFamily: t.ui, fontSize: 13, color: t.text }}>
          {sortedTrades.length === 0 ? (
            <tr>
              <td colSpan="17" style={{ padding: '32px 16px', textAlign: 'center', fontFamily: t.mono, color: t.dim }}>
                No trades found for the selected date range. Adjust the range or click &quot;Import Trades&quot; to pull logs.
              </td>
            </tr>
          ) : (
            sortedTrades.map(trade => {
              const isSelected = selectedTrades.has(trade.id);
              const { entryType, entryContext, closeType } = getParsedManualTags(trade.additional_tag);
              const isSaving = savingTradeId === trade.id;

              return (
                <tr
                  key={trade.id}
                  style={{
                    borderBottom: `1px solid ${t.border}`,
                    background: isSelected ? 'rgba(255,255,255,0.015)' : 'transparent',
                    transition: 'background 0.15s ease',
                    opacity: isSaving ? 0.6 : 1
                  }}
                  className="hover:bg-white/[0.01]"
                >
                  {/* Row Checkbox */}
                  <td style={{ padding: '10px 16px' }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleRow(trade.id)}
                      style={{ cursor: 'pointer', accentColor: t.accent }}
                    />
                  </td>

                  {/* Time (Entry & Exit Datetime) */}
                  <td style={{ padding: '10px 10px', whiteSpace: 'nowrap', fontFamily: t.mono, fontSize: 11.5, color: t.muted }}>
                    <div>{trade.entry_datetime}</div>
                    <div style={{ fontSize: 10.5, color: t.dim }}>{trade.exit_datetime}</div>
                  </td>

                  {/* Symbol */}
                  <td style={{ padding: '10px 10px', fontWeight: 700, fontFamily: t.mono }}>
                    {trade.symbol}
                  </td>

                  {/* Direction */}
                  <td style={{ padding: '10px 10px' }}>
                    <span
                      style={{
                        fontFamily: t.mono,
                        fontSize: 10,
                        fontWeight: 700,
                        borderRadius: 4,
                        padding: '2px 6px',
                        textTransform: 'uppercase',
                        color: trade.direction?.toLowerCase() === 'long' ? t.bull : t.bear,
                        background: trade.direction?.toLowerCase() === 'long' ? t.bullSoft : t.bearSoft,
                        border: `1px solid ${trade.direction?.toLowerCase() === 'long' ? t.bullBorder : t.bearBorder}`
                      }}
                    >
                      {trade.direction}
                    </span>
                  </td>

                  {/* Quantity Size */}
                  <td style={{ padding: '10px 10px', fontFamily: t.mono, fontWeight: 500 }}>
                    {trade.quantity}
                  </td>

                  {/* Entry & Exit Prices */}
                  <td style={{ padding: '10px 10px', fontFamily: t.mono, fontSize: 12, color: t.text }}>
                    <div>{trade.entry_price?.toFixed(2)}</div>
                    <div style={{ fontSize: 11, color: t.dim }}>{trade.exit_price?.toFixed(2)}</div>
                  </td>

                  {/* Gross PnL */}
                  <td
                    style={{
                      padding: '10px 10px',
                      fontFamily: t.mono,
                      fontWeight: 700,
                      color: trade.pnl > 0 ? t.success : trade.pnl < 0 ? t.error : t.muted
                    }}
                  >
                    {trade.pnl > 0 ? '+' : ''}{trade.pnl?.toFixed(2)}
                  </td>

                  {/* Net PnL */}
                  <td
                    style={{
                      padding: '10px 10px',
                      fontFamily: t.mono,
                      fontWeight: 700,
                      color: trade.net_pnl > 0 ? t.success : trade.net_pnl < 0 ? t.error : t.muted
                    }}
                  >
                    {trade.net_pnl > 0 ? '+' : ''}{trade.net_pnl?.toFixed(2)}
                  </td>

                  {/* Fees (Commission) */}
                  <td style={{ padding: '10px 10px', fontFamily: t.mono, color: t.muted }}>
                    ${trade.commission?.toFixed(2)}
                  </td>

                  {/* Duration */}
                  <td style={{ padding: '10px 10px', fontFamily: t.mono, color: t.muted, fontSize: 12 }}>
                    {formatDuration(trade.duration_seconds)}
                  </td>

                  {/* Setup Tag (Auto-tagged setup) */}
                  <td style={{ padding: '10px 10px' }}>
                    {trade.setup_tag ? (
                      <span
                        style={{
                          fontFamily: t.mono,
                          fontSize: 10,
                          fontWeight: 700,
                          borderRadius: 4,
                          padding: '2px 6px',
                          color: trade.setup_tag.includes('L') ? t.bull : t.bear,
                          background: trade.setup_tag.includes('L') ? t.bullSoft : t.bearSoft,
                          border: `1px solid ${trade.setup_tag.includes('L') ? t.bullBorder : t.bearBorder}`
                        }}
                      >
                        {trade.setup_tag}
                      </span>
                    ) : (
                      <span style={{ color: t.dim }}>-</span>
                    )}
                  </td>

                  {/* Key Indicators (Auto-tagged context) */}
                  <td style={{ padding: '10px 10px', minWidth: 150 }}>
                    {renderKeyIndicators(trade.key_indicators_tags)}
                  </td>

                  {/* Scoring Criteria */}
                  <td style={{ padding: '10px 10px', minWidth: 150 }}>
                    {renderCriteria(trade.scoring_criteria_tags)}
                  </td>

                  {/* Manual Tags (Three dropdowns: Entry Type, Context, Close Type) */}
                  <td style={{ padding: '8px 10px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {/* Entry Type */}
                      <select
                        value={entryType}
                        onChange={(e) => handleManualTagChange(trade, 'entry_type', e.target.value)}
                        style={{
                          background: t.inputBg,
                          color: entryType ? t.text : t.dim,
                          border: `1px solid ${t.border}`,
                          borderRadius: 4,
                          padding: '2px 6px',
                          fontSize: 11,
                          fontFamily: t.mono,
                          cursor: 'pointer',
                          outline: 'none'
                        }}
                      >
                        <option value="">-- Entry Type --</option>
                        {tagCategories.entry_type?.map(opt => (
                          <option key={opt} value={opt} style={{ background: t.panel }}>{opt}</option>
                        ))}
                      </select>

                      {/* Context */}
                      <select
                        value={entryContext}
                        onChange={(e) => handleManualTagChange(trade, 'entry_direct_context', e.target.value)}
                        style={{
                          background: t.inputBg,
                          color: entryContext ? t.text : t.dim,
                          border: `1px solid ${t.border}`,
                          borderRadius: 4,
                          padding: '2px 6px',
                          fontSize: 11,
                          fontFamily: t.mono,
                          cursor: 'pointer',
                          outline: 'none'
                        }}
                      >
                        <option value="">-- Context --</option>
                        {tagCategories.entry_direct_context?.map(opt => (
                          <option key={opt} value={opt} style={{ background: t.panel }}>{opt}</option>
                        ))}
                      </select>

                      {/* Close Type */}
                      <select
                        value={closeType}
                        onChange={(e) => handleManualTagChange(trade, 'close_type', e.target.value)}
                        style={{
                          background: t.inputBg,
                          color: closeType ? t.text : t.dim,
                          border: `1px solid ${t.border}`,
                          borderRadius: 4,
                          padding: '2px 6px',
                          fontSize: 11,
                          fontFamily: t.mono,
                          cursor: 'pointer',
                          outline: 'none'
                        }}
                      >
                        <option value="">-- Close Type --</option>
                        {tagCategories.close_type?.map(opt => (
                          <option key={opt} value={opt} style={{ background: t.panel }}>{opt}</option>
                        ))}
                      </select>
                    </div>
                  </td>

                  {/* Rating (0-100) - Read-only display */}
                  <td style={{ padding: '10px 10px', fontFamily: t.mono, textAlign: 'center', color: trade.setup_rating !== null && trade.setup_rating !== undefined ? t.text : t.dim }}>
                    {trade.setup_rating !== null && trade.setup_rating !== undefined ? trade.setup_rating : '-'}
                  </td>

                  {/* Comments Inline Monospace */}
                  <td style={{ padding: '10px 10px' }}>
                    <input
                      type="text"
                      placeholder="Add review comments..."
                      value={localComments[trade.id] ?? ''}
                      onChange={(e) => {
                        const val = e.target.value;
                        setLocalComments(prev => ({ ...prev, [trade.id]: val }));
                      }}
                      onBlur={() => {
                        onUpdateTrade(trade.id, { comments: localComments[trade.id] });
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') e.target.blur();
                      }}
                      style={{
                        background: 'transparent',
                        color: t.text,
                        border: `1px solid transparent`,
                        borderRadius: 4,
                        padding: '4px 8px',
                        fontSize: 12.5,
                        width: '100%',
                        minWidth: 150,
                        outline: 'none',
                        transition: 'border-color 0.15s, background 0.15s'
                      }}
                      className="hover:border-white/10 hover:bg-white/[0.02] focus:border-white/20 focus:bg-white/[0.04]"
                    />
                  </td>



                  {/* Row Delete Button */}
                  <td style={{ padding: '10px 16px', textAlign: 'center' }}>
                    <button
                      onClick={() => onDeleteTrade(trade)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: t.dim,
                        cursor: 'pointer',
                        padding: 4,
                        borderRadius: 4,
                        transition: 'color 0.15s, background 0.15s'
                      }}
                      className="hover:text-red-400 hover:bg-red-500/10"
                      title="Delete Trade"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
