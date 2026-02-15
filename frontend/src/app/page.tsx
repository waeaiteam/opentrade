'use client';

import { useEffect, useState } from 'react';
import styles from './page.module.css';

interface Trade {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  status: string;
  created_at: string;
}

interface Position {
  symbol: string;
  quantity: number;
  entry_price: number;
  pnl: number;
  pnl_percent: number;
}

interface DashboardData {
  balance: number;
  positions: Position[];
  recent_trades: Trade[];
}

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboard();
    const interval = setInterval(fetchDashboard, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchDashboard = async () => {
    try {
      const res = await fetch('/api/v1/status');
      if (res.ok) {
        const data = await res.json();
        setData({
          balance: data.balance || 10000,
          positions: data.positions || [],
          recent_trades: data.recent_trades || [],
        });
      }
    } catch {
      // API not available, show demo data
      setData({
        balance: 10000,
        positions: [
          { symbol: 'BTC/USDT', quantity: 0.1, entry_price: 68000, pnl: 500, pnl_percent: 7.4 },
          { symbol: 'ETH/USDT', quantity: 2, entry_price: 2000, pnl: 100, pnl_percent: 2.5 },
        ],
        recent_trades: [
          { id: '1', symbol: 'BTC/USDT', side: 'BUY', quantity: 0.1, price: 67500, status: 'FILLED', created_at: new Date().toISOString() },
        ],
      });
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className={styles.loading}>Loading OpenTrade...</div>;

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <h1>🚀 OpenTrade</h1>
        <p>Enterprise AI Trading System</p>
      </header>

      <section className={styles.stats}>
        <div className={styles.card}>
          <h3>Balance</h3>
          <p className={styles.value}>${data?.balance?.toLocaleString() || '0'}</p>
        </div>
        <div className={styles.card}>
          <h3>Positions</h3>
          <p className={styles.value}>{data?.positions?.length || 0}</p>
        </div>
        <div className={styles.card}>
          <h3>Status</h3>
          <p className={styles.value}>🟢 Online</p>
        </div>
      </section>

      {data?.positions && data.positions.length > 0 && (
        <section className={styles.section}>
          <h2>📊 Positions</h2>
          <div className={styles.grid}>
            {data.positions.map((pos) => (
              <div key={pos.symbol} className={styles.position}>
                <span className={styles.symbol}>{pos.symbol}</span>
                <span className={styles.quantity}>{pos.quantity}</span>
                <span className={pos.pnl >= 0 ? styles.pnl_pos : styles.pnl_neg}>
                  {pos.pnl >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(2)}%
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className={styles.section}>
        <h2>⚡ Quick Actions</h2>
        <div className={styles.actions}>
          <button className={styles.btn} disabled>Buy BTC</button>
          <button className={styles.btn} disabled>Sell BTC</button>
          <button className={styles.btn} disabled>Close All</button>
        </div>
        <p className={styles.hint}>Connect API to enable trading</p>
      </section>

      <footer className={styles.footer}>
        <p>Powered by LangGraph Multi-Agent System</p>
        <p>Built with ❤️ by OpenTrade</p>
      </footer>
    </main>
  );
}
