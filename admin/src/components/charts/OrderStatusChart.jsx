// src/components/charts/OrderStatusChart.jsx
import React, { useEffect, useRef, useState } from 'react';
import { 
  PieChart, 
  Pie, 
  Cell, 
  ResponsiveContainer,
  Tooltip,
  Legend
} from 'recharts';

const RADIAN = Math.PI / 180;

const OrderStatusChart = ({ orders }) => {
  const containerRef = useRef(null);
  const [sizes, setSizes] = useState(
    () => (typeof window !== 'undefined' && window.innerWidth < 480)
      ? { outer: 60, inner: 30, fontSize: 10 }
      : { outer: 80, inner: 40, fontSize: 11 }
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;

    const update = () => {
      const width = el.clientWidth;
      const small = width < 480;
      setSizes({
        outer: small ? 60 : 80,
        inner: small ? 30 : 40,
        fontSize: small ? 10 : 11,
      });
    };

    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener('resize', update);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', update);
    };
  }, []);

  // Shipped + Out for Delivery are one in-transit state here: combined
  // they clear the label threshold instead of overlapping each other.
  // Per-status counts still break out in the Reports cards and tooltips.
  const inTransit =
    (orders.shipped || 0) + (orders.out_for_delivery || 0);
  const statusData = [
    { name: 'Pending', value: orders.pending || 0, color: '#F59E0B' },
    { name: 'Confirmed', value: orders.confirmed || 0, color: '#3B82F6' },
    { name: 'Shipped', value: inTransit, color: '#8B5CF6' },
    { name: 'Delivered', value: orders.delivered || 0, color: '#10B981' },
    { name: 'Cancelled', value: orders.cancelled || 0, color: '#EF4444' },
    { name: 'RTO', value: orders.rto || 0, color: '#F97316' },
    { name: 'Refunded', value: orders.refunded || 0, color: '#6B7280' },
  ].filter(item => item.value > 0);

  // Outside labels overlap once slices get small or numerous (8 statuses
  // now), and clamping them inside the card stacks them on each other.
  // So: label only slices big enough to own their space; everything else
  // lives in the legend (with counts) + tooltip. Small screens are
  // stricter since there is less room per label.
  const small = sizes.outer < 80;
  const labelThreshold = small ? 0.12 : 0.06;

  const renderLabel = ({ cx, cy, midAngle, outerRadius, name, percent }) => {
    if (!percent || percent < labelThreshold) return null;
    // Position each label just outside its slice (official Recharts pattern).
    // On small cards the "Name (xx%)" text is wider than the plot, so
    // shrink to short name + clamp the anchor point inside the card —
    // otherwise side labels render outside the border.
    const labelText = small
      ? `${String(name).slice(0, 6)} (${(percent * 100).toFixed(0)}%)`
      : `${name} (${(percent * 100).toFixed(0)}%)`;
    const labelOffset = small ? 8 : 14;
    const radius = outerRadius + labelOffset;
    const rawX = cx + radius * Math.cos(-midAngle * RADIAN);
    const rawY = cy + radius * Math.sin(-midAngle * RADIAN);
    // PieChart has no measured width here; clamp against the known
    // card geometry: half-width ≈ outer radius + side padding.
    // Keeps labels inside instead of bleeding past the card edge.
    const halfSpan = outerRadius + (small ? 78 : 110);
    const x = Math.max(cx - halfSpan, Math.min(cx + halfSpan, rawX));
    return (
      <text
        x={x}
        y={rawY}
        textAnchor={x > cx ? 'start' : 'end'}
        dominantBaseline="middle"
        fill="var(--foreground)"
        fontSize={sizes.fontSize}
      >
        {labelText}
      </text>
    );
  };

  if (statusData.length === 0) {
    return (
      <div className="w-full h-48 sm:h-56 flex items-center justify-center text-sm text-muted-foreground">
        No orders in this range
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full h-72 sm:h-80 min-w-0 overflow-hidden">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <Pie
            data={statusData}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={renderLabel}
            outerRadius={sizes.outer}
            innerRadius={sizes.inner}
            fill="#8884d8"
            dataKey="value"
            paddingAngle={2}
          >
            {statusData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip 
            formatter={(value, name) => [value, name]}
            contentStyle={{ 
              background: 'var(--card)',
              color: 'var(--foreground)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
            }}
            itemStyle={{ color: 'var(--foreground)' }}
            labelStyle={{ color: 'var(--foreground)' }}
          />
          <Legend
            verticalAlign="bottom"
            height={52}
            iconType="circle"
            formatter={(value, entry) => `${value} (${entry?.payload?.value ?? 0})`}
            wrapperStyle={{ color: 'var(--foreground)', fontSize: 12, lineHeight: '20px' }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};

export default OrderStatusChart;