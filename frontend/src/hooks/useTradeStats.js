import { useMemo } from 'react';

/**
 * Custom hook to calculate trading statistics from filtered trades
 */
export function useTradeStats(filteredTrades) {
    const stats = useMemo(() => {
        if (!filteredTrades || filteredTrades.length === 0) {
            return {
                summary: {
                    total_pnl: 0,
                    gross_pnl: 0,
                    total_fees: 0,
                    commission_per_trade: 0,
                    win_rate: 0,
                    total_trades: 0,
                    expected_value: 0,
                    profit_factor: 0,
                    best_trade: 0,
                    worst_trade: 0,
                    avg_win: 0,
                    avg_loss: 0
                },
                duration: {
                    avg_duration: 0,
                    avg_win_duration: 0,
                    avg_loss_duration: 0
                },
                direction: {
                    long_pct: 0,
                    short_pct: 0
                }
            };
        }

        let totalPnL = 0;
        let totalFees = 0;
        let grossWin = 0;
        let grossLoss = 0;
        let wins = 0;
        let losses = 0;
        let maxWin = -Infinity;
        let maxLoss = Infinity;
        let totalDuration = 0;
        let totalWinDuration = 0;
        let totalLossDuration = 0;

        let longs = 0;
        let shorts = 0;

        filteredTrades.forEach(t => {
            const pnl = t.net_pnl ?? t.pnl ?? 0;
            const fees = t.commission ?? 0;
            const duration = t.duration_seconds ?? 0;

            totalPnL += pnl;
            totalFees += fees;
            totalDuration += duration;

            if (pnl > 0) {
                wins++;
                grossWin += pnl;
                maxWin = Math.max(maxWin, pnl);
                totalWinDuration += duration;
            } else {
                losses++;
                grossLoss += Math.abs(pnl);
                maxLoss = Math.min(maxLoss, pnl);
                totalLossDuration += duration;
            }

            const dir = (t.direction || '').toLowerCase();
            if (dir.includes('long') || dir.includes('buy')) longs++;
            else if (dir.includes('short') || dir.includes('sell')) shorts++;
        });

        const totalTrades = filteredTrades.length;
        const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
        const pf = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 999.99 : 0;
        const avgWin = wins > 0 ? grossWin / wins : 0;
        const avgLoss = losses > 0 ? -grossLoss / losses : 0;
        const ev = totalTrades > 0 ? totalPnL / totalTrades : 0;

        if (maxWin === -Infinity) maxWin = 0;
        if (maxLoss === Infinity) maxLoss = 0;

        return {
            summary: {
                total_pnl: totalPnL,
                gross_pnl: totalPnL + totalFees,
                total_fees: totalFees,
                commission_per_trade: totalTrades > 0 ? totalFees / totalTrades : 0,
                win_rate: winRate,
                total_trades: totalTrades,
                expected_value: ev,
                profit_factor: pf,
                best_trade: maxWin,
                worst_trade: maxLoss,
                avg_win: avgWin,
                avg_loss: avgLoss
            },
            duration: {
                avg_duration: totalTrades > 0 ? totalDuration / totalTrades : 0,
                avg_win_duration: wins > 0 ? totalWinDuration / wins : 0,
                avg_loss_duration: losses > 0 ? totalLossDuration / losses : 0
            },
            direction: {
                long_pct: totalTrades > 0 ? (longs / totalTrades) * 100 : 0,
                short_pct: totalTrades > 0 ? (shorts / totalTrades) * 100 : 0
            }
        };
    }, [filteredTrades]);

    return stats;
}
