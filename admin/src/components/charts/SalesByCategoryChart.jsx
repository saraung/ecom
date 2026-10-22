// src/components/charts/SalesByCategoryChart.jsx
//
// Vertical "Sales by Category" bar chart for the admin dashboard.
//
// Replaces the old UserDistributionChart in the same slot (same vertical
// bar look), but plots last-30d revenue per ROOT category instead of role
// counts. Top products keeps its ranked-list UI, so the two widgets stay
// visually distinct.
//
// Data contract (dashboardData.sales_by_category, 30d window):
//   [{ category_id, category_name, revenue, quantity_sold }, ...]
// Top 4 roots + one "Others" bucket (category_id: null), so this never
// renders more than 5 bars no matter how deep/wide the category tree gets.
import React, { useEffect, useRef, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import { formatNumber, formatPrice, formatShort } from '../../utils/format';

const BAR_COLORS = ['#3B82F6', '#8B5CF6', '#10B981', '#F59E0B'];
const OTHERS_COLOR = '#6B7280';

const formatCurrencyShort = (value) => formatShort(value);

// Keep axis ticks compact; the full name is in the tooltip.
// NOTE: truncation length must stay generous — the dashboard passes a
// client-side fallback that synthesises an "Others" bucket from leftover
// revenue (see Dashboard.jsx salesByCategory). Over-truncating (e.g. 6
// chars) makes every bar read "Others" on real phones. 10 chars keeps
// real names distinguishable: "Electron…" vs "Others".
const truncateTick = (name, len = 10) => {
  const s = String(name || '');
  return s.length > len ? `${s.slice(0, len)}…` : s;
};

const SalesByCategoryChart = ({ data = [], max = 5, onSelect }) => {
  // Mobile responsiveness: measure the actual card width (not window) so the
  // chart adapts inside any layout — same pattern as RevenueChart.
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

  const rows = (Array.isArray(data) ? data.slice(0, max) : []).map((item) => ({
    ...item,
    name: item?.category_name || 'Others',
    revenue: Number(item?.revenue) || 0,
    quantity_sold: Number(item?.quantity_sold) || 0,
    fill: item?.category_id == null ? OTHERS_COLOR : BAR_COLORS[0],
  }));
  rows.forEach((row, i) => {
    if (row.category_id != null) row.fill = BAR_COLORS[i % BAR_COLORS.length];
  });

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
        <BarChart3 size={32} className="mb-2 text-muted-foreground" />
        <p className="text-sm">No category sales in the last 30 days</p>
      </div>
    );
  }

  const handleClick = (entry) => {
    if (typeof onSelect === 'function' && entry?.category_id != null) {
      onSelect(entry);
    }
  };

  return (
    <div ref={containerRef} className="w-full h-64 sm:h-80 min-w-0 overflow-hidden">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          margin={isSmall ? { top: 20, right: 4, left: -8, bottom: 0 } : { top: 20, right: 30, left: 20, bottom: 5 }}
          barCategoryGap={isSmall ? '30%' : '20%'}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: isSmall ? 10 : 12, fill: 'var(--muted-foreground)' }}
            tickFormatter={(name) => truncateTick(name, isSmall ? 8 : 10)}
            interval={0}
            angle={isSmall ? -20 : 0}
            dy={isSmall ? 8 : 0}
            height={isSmall ? 42 : 30}
            tickMargin={isSmall ? 4 : 8}
            stroke="var(--border)"
          />
          <YAxis
            tickFormatter={formatCurrencyShort}
            tick={{ fontSize: isSmall ? 10 : 11, fill: 'var(--muted-foreground)' }}
            width={isSmall ? 44 : 60}
            stroke="var(--border)"
          />
          <Tooltip
            formatter={(value, _name, props) => {
              const units = Number(props?.payload?.quantity_sold) || 0;
              return [
                `${formatPrice(value, { decimals: 0 })} (${formatNumber(units)} units)`,
                'Revenue',
              ];
            }}
            labelFormatter={(label) => label}
            wrapperStyle={isSmall ? { maxWidth: '90vw', fontSize: 12 } : undefined}
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
          <Legend
            wrapperStyle={{ color: 'var(--foreground)', fontSize: isSmall ? 11 : 14 }}
            iconSize={isSmall ? 10 : 14}
          />
          <Bar
            dataKey="revenue"
            radius={[4, 4, 0, 0]}
            name="Revenue (30d)"
            barSize={isSmall ? 24 : undefined}
            onClick={handleClick}
            style={typeof onSelect === 'function' ? { cursor: 'pointer' } : undefined}
          >
            {rows.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default SalesByCategoryChart;
