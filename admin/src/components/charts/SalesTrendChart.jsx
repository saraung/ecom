// src/components/charts/SalesTrendChart.jsx
import React from 'react';
import { formatDay, formatNumber, formatPrice, formatShort } from '../../utils/format';
import {
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

/**
 * Daily sales trend for the dashboard.
 * Receives real data from GET /admin/dashboard → sales_trend:
 *   [{ date: 'YYYY-MM-DD', sales: number, orders: number }, ...]
 * (last 7 days, zero-filled by the backend).
 */
const SalesTrendChart = ({ data = [] }) => {
  const trendData = (data || []).map((d) => {
    const dt = new Date(`${d.date}T00:00:00`);
    const valid = !Number.isNaN(dt.getTime());
    return {
      name: valid ? formatDay(dt, { weekday: 'short' }) : d.date,
      fullDate: valid ? formatDay(dt, { day: 'numeric', month: 'short' }) : d.date,
      sales: Number(d.sales) || 0,
      orders: Number(d.orders) || 0,
    };
  });

  const formatYAxis = (value) => formatShort(value);

  if (!trendData.length) {
    return (
      <div className="w-full h-64 sm:h-80 flex items-center justify-center text-muted-foreground">
        No sales data available yet
      </div>
    );
  }

  return (
    <div className="w-full h-64 sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={trendData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <defs>
            <linearGradient id="salesGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.8} />
              <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 12, fill: 'var(--muted-foreground)' }}
            stroke="var(--border)"
          />
          <YAxis
            tickFormatter={formatYAxis}
            tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
            stroke="var(--border)"
          />
          <Tooltip
            labelFormatter={(_label, payload) => payload?.[0]?.payload?.fullDate || ''}
            formatter={(value, name) => [
              name === 'Sales'
                ? formatPrice(value, { decimals: 0 })
                : `${formatNumber(value)} orders`,
              name,
            ]}
            contentStyle={{
              background: 'var(--card)',
              color: 'var(--foreground)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
            }}
            itemStyle={{ color: 'var(--foreground)' }}
            labelStyle={{ color: 'var(--foreground)' }}
          />
          <Legend wrapperStyle={{ color: 'var(--foreground)' }} />
          <Area
            type="monotone"
            dataKey="sales"
            stroke="var(--primary)"
            fillOpacity={1}
            fill="url(#salesGradient)"
            name="Sales"
          />
          <Line
            type="monotone"
            dataKey="orders"
            stroke="var(--success)"
            strokeWidth={2}
            name="Orders"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

export default SalesTrendChart;