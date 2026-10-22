import React, { useEffect, useRef, useState } from 'react';
import { formatNumber, formatPrice, formatShort } from '../../utils/format';
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

const RevenueChart = ({ data }) => {
  const containerRef = useRef(null);
  const [isSmall, setIsSmall] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 480
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;

    const update = () => setIsSmall(el.clientWidth < 480);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener('resize', update);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', update);
    };
  }, []);

  // Period-over-period revenue + orders. Product ranking is handled by
  // TopProductsChart — a vertical bar chart with many category labels is
  // unreadable, so this component only ever plots the 4 fixed periods.
  const chartData = [
    {
      name: 'Today',
      revenue: data.today.revenue || 0,
      orders: data.today.orders || 0,
    },
    {
      name: 'This Week',
      revenue: data.this_week.revenue || 0,
      orders: data.this_week.orders || 0,
    },
    {
      name: 'This Month',
      revenue: data.this_month.revenue || 0,
      orders: data.this_month.orders || 0,
    },
    {
      name: 'Total',
      revenue: data.total.revenue || 0,
      orders: data.total.orders || 0,
    },
  ];

  const formatCurrency = (value) => formatShort(value);

  const SHORT_NAMES = {
    'Today': 'Today',
    'This Week': 'Week',
    'This Month': 'Month',
    'Total': 'Total',
  };

  const formatTickLabel = (name) => (isSmall ? SHORT_NAMES[name] || name : name);

  const formatTooltipValue = (value, name) => {
    if (name === 'Revenue') return [formatPrice(value, { decimals: 0 }), 'Revenue'];
    return [formatNumber(value), 'Orders'];
  };

  return (
    <div ref={containerRef} className="w-full h-64 sm:h-80">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={chartData}
          margin={isSmall ? { top: 20, right: 4, left: 4, bottom: 0 } : { top: 20, right: 30, left: 20, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: isSmall ? 10 : 12, fill: 'var(--muted-foreground)' }}
            interval={0}
            tickFormatter={formatTickLabel}
            tickMargin={isSmall ? 4 : 8}
            stroke="var(--border)"
          />

          {/* Left axis: revenue, currency-formatted */}
          <YAxis
            yAxisId="revenue"
            orientation="left"
            tickFormatter={formatCurrency}
            tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
            stroke="var(--border)"
          />

          {/* Right axis: units/orders count */}
          <YAxis
            yAxisId="orders"
            orientation="right"
            allowDecimals={false}
            tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
            stroke="var(--border)"
          />

          <Tooltip
            formatter={formatTooltipValue}
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

          <Bar
            yAxisId="revenue"
            dataKey="revenue"
            fill="var(--primary)"
            radius={[4, 4, 0, 0]}
            name="Revenue"
            barSize={isSmall ? 24 : 40}
          />
          <Line
            yAxisId="orders"
            type="monotone"
            dataKey="orders"
            stroke="var(--success)"
            strokeWidth={2}
            dot={{ r: 4 }}
            name="Orders"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

export default RevenueChart;