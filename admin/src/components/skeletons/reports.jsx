// src/components/skeletons/reports.jsx
import React from 'react';
import { RefreshCw, Download, Calendar, DollarSign, TrendingUp, ShoppingBag } from 'lucide-react';
import { Card, Btn, SectionTitle, Count, Skeleton } from './_shared';

export const ReportsSkeleton = () => (
  <div className="space-y-6">
    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Reports &amp; Analytics</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Showing data from <Count w="w-16" /> to <Count w="w-24" />
        </p>
      </div>
      <div className="flex flex-col sm:flex-row w-full sm:w-auto gap-2 sm:gap-3">
        <Btn className="px-4 py-2.5 sm:py-2 gap-2 border border-input rounded-lg hover:bg-muted transition-colors justify-center">
          <Download size={18} />
          Export
        </Btn>
        <Btn className="bg-primary text-primary-foreground px-4 py-2.5 sm:py-2 rounded-lg gap-2 justify-center">
          <RefreshCw size={18} />
          Refresh
        </Btn>
      </div>
    </div>

    <Card className="p-4">
      <div className="flex flex-col gap-4">
        {/* Quick date presets */}
        <div className="flex flex-wrap gap-2">
          {['Today', 'Last 7 Days', 'Last 30 Days', 'Last 90 Days', 'This Year'].map((label) => (
            <button
              key={label}
              type="button"
              className="px-3 py-1.5 text-xs font-medium bg-muted text-muted-foreground rounded-lg"
            >
              {label}
            </button>
          ))}
        </div>

        {/* Custom date range + group by */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <Calendar size={18} className="text-muted-foreground" />
            <label className="text-sm font-medium text-muted-foreground">From:</label>
            <input
              type="date"
              disabled
              className="px-3 py-1.5 border border-input rounded-lg bg-transparent"
              aria-label="From date"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-muted-foreground">To:</label>
            <input
              type="date"
              disabled
              className="px-3 py-1.5 border border-input rounded-lg bg-transparent"
              aria-label="To date"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-muted-foreground">Group By:</label>
            <select
              disabled
              className="px-3 py-1.5 border border-input rounded-lg bg-transparent"
              aria-label="Group by"
            >
              <option>Day</option>
              <option>Week</option>
              <option>Month</option>
            </select>
          </div>
        </div>
      </div>
    </Card>

    {/* Tabs */}
    <div className="flex gap-2 border-b border-border overflow-x-auto">
      {['Overview', 'Products', 'Orders', 'Customers'].map((tab, i) => (
        <button
          key={tab}
          type="button"
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap ${
            i === 0
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground'
          }`}
        >
          {tab}
        </button>
      ))}
    </div>

    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {[
        { title: 'Total Revenue (Filtered)', icon: DollarSign, chip: 'bg-success/10 text-success', sub: true },
        { title: 'Total Orders (Filtered)', icon: ShoppingBag, chip: 'bg-orange-500/10 text-orange-500', sub: false },
        { title: 'Average Order Value', icon: TrendingUp, chip: 'bg-primary-soft text-primary', sub: false },
      ].map(({ title, icon: Icon, chip, sub }) => (
        <Card key={title} className="p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground">{title}</p>
              <Skeleton className="h-8 w-24 mt-2" />
              {/* Prior-period delta line */}
              <Skeleton className="h-3 w-28 mt-2" />
              {sub === true && (
                <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                  <Count w="w-12" className="inline-block h-3 align-middle" /> to
                  <Count w="w-16" className="inline-block h-3 align-middle" />
                </p>
              )}
            </div>
            <div className={`${chip} p-3 rounded-lg flex-shrink-0`}>
              <Icon size={24} />
            </div>
          </div>
        </Card>
      ))}
    </div>

    {/* Revenue Trend chart - static title + plot-area skeleton */}
    <Card className="p-6">
      <SectionTitle>Revenue Trend</SectionTitle>
      <p className="text-sm text-muted-foreground mb-4">
        Grouped by <Count w="w-12" className="inline-block h-3 align-middle" /> · hover or tap a point for exact values
      </p>
      <Skeleton className="h-64 sm:h-72 w-full rounded-lg" />
    </Card>

    {/* Revenue Breakdown table - static header row */}
    <Card className="p-6">
      <SectionTitle>Revenue Breakdown</SectionTitle>
      <div className="overflow-x-auto mt-4">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              {[
                { label: 'Period', align: 'text-left' },
                { label: 'Revenue', align: 'text-right' },
                { label: 'Discounts', align: 'text-right' },
                { label: 'Tax', align: 'text-right' },
                { label: 'Shipping', align: 'text-right' },
                { label: 'Refunds', align: 'text-right' },
                { label: 'Net Revenue', align: 'text-right' },
              ].map(({ label, align }) => (
                <th
                  key={label}
                  className={`px-4 py-3 text-xs font-medium text-muted-foreground uppercase ${align}`}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {Array.from({ length: 4 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-20" />
                </td>
                {[0, 1, 2, 3, 4, 5].map((c) => (
                  <td key={c} className="px-4 py-3">
                    <Skeleton className="h-4 w-16 ml-auto" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  </div>
);
