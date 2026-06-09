import React, { useState, useEffect } from 'react';
import { useReview } from '../hooks/useReview';
import { t, CardHeader } from './ui';
import { CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

export default function PlanVsExecution({ sessionDate }) {
  const { loadPlanVsExecution } = useReview();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await loadPlanVsExecution(sessionDate);
        if (mounted) setData(res);
      } catch (err) {
        console.error(err);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchData();
    return () => { mounted = false; };
  }, [loadPlanVsExecution, sessionDate]);

  if (loading) {
    return (
      <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 300 }}>
        <span style={{ fontFamily: t.mono, fontSize: 12.5, color: t.dim }} className="badge-running">
          Loading Plan vs Execution data...
        </span>
      </div>
    );
  }

  if (!data || !data.summary) {
    return (
      <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 300 }}>
        <span style={{ fontFamily: t.mono, fontSize: 12.5, color: t.dim }}>
          No plan data available for {sessionDate}
        </span>
      </div>
    );
  }

  const { scenarios, unplanned_trades, summary } = data;
  const alignmentPercentage = summary.total_trades > 0 
    ? Math.round((summary.aligned_count / summary.total_trades) * 100) 
    : 0;

  const renderTradeList = (trades, type) => {
    if (!trades || trades.length === 0) {
      return <div style={{ color: t.dim, fontSize: 11, fontStyle: 'italic', padding: 8 }}>None</div>;
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
        {trades.map(tr => (
          <div key={tr.id} style={{
            display: 'flex', justifyContent: 'space-between', padding: '6px 10px',
            background: 'rgba(255,255,255,0.02)', border: `1px solid ${type === 'aligned' ? t.bullBorder : t.bearBorder}`,
            borderRadius: 4, fontSize: 12, fontFamily: t.mono
          }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <span style={{ color: tr.direction?.toLowerCase() === 'long' ? t.bull : t.bear, fontWeight: 700 }}>
                {tr.direction}
              </span>
              <span style={{ color: t.text }}>{tr.entry_datetime?.split(' ')[1] || ''}</span>
              <span style={{ color: t.muted }}>[{tr.setup_tag || 'none'}]</span>
            </div>
            <span style={{ color: (tr.net_pnl || 0) >= 0 ? t.bull : t.bear, fontWeight: 700 }}>
              ${(tr.net_pnl || 0).toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary Bar */}
      <div style={{ 
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', 
        padding: '12px 20px', background: t.panel2, border: `1px solid ${t.border}`, borderRadius: 6
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <TargetIcon size={20} color={t.text} />
          <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Plan Adherence</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <span style={{ fontSize: 11, color: t.dim, textTransform: 'uppercase' }}>Aligned</span>
            <span style={{ fontSize: 14, fontFamily: t.mono, fontWeight: 700, color: t.bull }}>{summary.aligned_count}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <span style={{ fontSize: 11, color: t.dim, textTransform: 'uppercase' }}>Unaligned</span>
            <span style={{ fontSize: 14, fontFamily: t.mono, fontWeight: 700, color: t.bear }}>{summary.unaligned_count}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <span style={{ fontSize: 11, color: t.dim, textTransform: 'uppercase' }}>Unplanned</span>
            <span style={{ fontSize: 14, fontFamily: t.mono, fontWeight: 700, color: '#ffb300' }}>{summary.unplanned_count}</span>
          </div>
          <div style={{ height: 30, width: 1, background: t.border }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 24, fontWeight: 800, fontFamily: t.mono, color: alignmentPercentage >= 80 ? t.bull : (alignmentPercentage >= 50 ? '#ffb300' : t.bear) }}>
              {alignmentPercentage}%
            </span>
            <span style={{ fontSize: 11, color: t.dim, maxWidth: 60, lineHeight: 1.2 }}>alignment score</span>
          </div>
        </div>
      </div>

      {/* Scenarios Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 16 }}>
        {scenarios.map((sc, idx) => (
          <div key={idx} className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <span style={{ 
                padding: '4px 10px', background: t.bullSoft, color: t.bull, 
                border: `1px solid ${t.bullBorder}`, borderRadius: 4, fontSize: 12, fontWeight: 700 
              }}>
                {sc.setup_type || `Scenario ${idx + 1}`}
              </span>
            </div>
            <div style={{ fontSize: 13, color: t.text, lineHeight: 1.5, padding: '8px 12px', background: 'rgba(255,255,255,0.02)', borderRadius: 4 }}>
              <strong>Rationale:</strong> {sc.rationale || 'N/A'}<br/>
              <strong>Targets:</strong> {sc.targets || 'N/A'}
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 4 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: t.bull }}>
                  <CheckCircle2 size={14} /> Aligned Executions
                </div>
                {renderTradeList(sc.aligned_trades, 'aligned')}
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: t.bear }}>
                  <XCircle size={14} /> Unaligned Executions
                </div>
                {renderTradeList(sc.unaligned_trades, 'unaligned')}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Unplanned Trades */}
      {unplanned_trades && unplanned_trades.length > 0 && (
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: '#ffb300', marginBottom: 12 }}>
            <AlertCircle size={16} /> Unplanned Trades ({unplanned_trades.length})
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 10 }}>
            {unplanned_trades.map(tr => (
              <div key={tr.id} style={{
                display: 'flex', justifyContent: 'space-between', padding: '6px 10px',
                background: 'rgba(255,179,0,0.05)', border: `1px solid rgba(255,179,0,0.2)`,
                borderRadius: 4, fontSize: 12, fontFamily: t.mono
              }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <span style={{ color: tr.direction?.toLowerCase() === 'long' ? t.bull : t.bear, fontWeight: 700 }}>
                    {tr.direction}
                  </span>
                  <span style={{ color: t.text }}>{tr.entry_datetime?.split(' ')[1] || ''}</span>
                </div>
                <span style={{ color: (tr.net_pnl || 0) >= 0 ? t.bull : t.bear, fontWeight: 700 }}>
                  ${(tr.net_pnl || 0).toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Simple Target Icon
function TargetIcon(props) {
  return (
    <svg width={props.size || 24} height={props.size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <circle cx="12" cy="12" r="10"></circle>
      <circle cx="12" cy="12" r="6"></circle>
      <circle cx="12" cy="12" r="2"></circle>
    </svg>
  );
}
