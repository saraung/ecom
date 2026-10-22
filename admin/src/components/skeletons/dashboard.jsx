// src/components/skeletons/dashboard.jsx
import React from 'react';
import { RefreshCw, ChevronRight, DollarSign, Package, BarChart3, TrendingUp, PieChart, Users, ShoppingBag } from 'lucide-react';
import { Card, Btn, SectionTitle, Count, ChartCard, Skeleton } from './_shared';

export const DashboardSkeleton = () => (
  <div className="space-y-4 sm:space-y-6 px-2 sm:px-0">
    {/* Header - static real text */}
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
          Welcome back! Here&apos;s what&apos;s happening with your store.
        </p>
      </div>
      <Btn className="self-start sm:self-auto p-2 rounded-lg" title="Refresh data">
        <RefreshCw size={16} className="text-muted-foreground" />
      </Btn>
    </div>

    {/* Stat cards - static titles/subtitles, dynamic values are bars */}
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-4">
      {[
        { title: 'Revenue', prefix: 'Today: ', suffix: '', icon: DollarSign, chip: 'bg-success/10 text-success' },
        { title: 'Orders', prefix: '', suffix: ' pending', icon: ShoppingBag, chip: 'bg-accent/10 text-accent' },
        { title: 'Products', text: 'In store', icon: Package, chip: 'bg-info/10 text-info' },
        { title: 'Users', prefix: '', suffix: ' active', icon: Users, chip: 'bg-warning/10 text-warning' },
      ].map(({ title, prefix, suffix, text, icon: Icon, chip }) => (
        <Card key={title} className="p-4 sm:p-6">
          <div className="flex items-start justify-between gap-2 min-w-0">
            <div className="flex-1 min-w-0">
              <p className="text-xs sm:text-sm text-muted-foreground font-medium truncate">{title}</p>
              <Skeleton className="h-6 sm:h-8 w-24 mt-2" />
              {(text || prefix !== undefined) && (
                <p className="text-xs text-muted-foreground mt-2 truncate flex items-center gap-1">
                  {text || (
                    <>
                      {prefix}
                      <Count w="w-12" className="inline-block h-3 align-middle" />
                      {suffix}
                    </>
                  )}
                </p>
              )}
            </div>
            <div className={`${chip} p-2.5 sm:p-3 rounded-lg flex-shrink-0`}>
              <Icon size={20} />
            </div>
          </div>
        </Card>
      ))}
    </div>

    {/* Revenue Overview + Sales Trend - static card titles */}
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
      <ChartCard
        title="Revenue Overview"
        icon={BarChart3}
        action={(
          <Btn className="text-xs sm:text-sm text-primary font-medium gap-1">
            Details
            <ChevronRight size={16} />
          </Btn>
        )}
      />
      <ChartCard
        title="Sales Trend"
        icon={TrendingUp}
        action={(
          <Btn className="text-xs sm:text-sm text-primary font-medium gap-1">
            Details
            <ChevronRight size={16} />
          </Btn>
        )}
      />
    </div>

    {/* Order Distribution + User Distribution */}
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
      <ChartCard title="Order Distribution" icon={PieChart} />
      <ChartCard title="User Distribution" icon={Users} />
    </div>

    {/* Recent Orders */}
    <Card className="p-4 sm:p-6">
      <div className="flex items-center justify-between gap-3 mb-4">
        <SectionTitle className="text-base sm:text-lg font-semibold text-foreground">
          <ShoppingBag size={20} className="text-muted-foreground" />
          Recent Orders
        </SectionTitle>
        <Btn className="text-xs sm:text-sm text-primary font-medium gap-1">
          View All
        </Btn>
      </div>
      <div className="hidden sm:block divide-y divide-border">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 py-3">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-6 w-20 rounded-full ml-auto" />
          </div>
        ))}
      </div>
      {/* Mobile cards (below sm) - muted cards like the real page */}
      <div className="sm:hidden space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="p-4 bg-muted rounded-lg space-y-2">
            <div className="flex items-center justify-between">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
            </div>
            <div className="flex items-center justify-between">
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-3 w-16" />
            </div>
          </div>
        ))}
      </div>
    </Card>

    {/* Quick Actions - five colored buttons like the real page */}
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">
      {[
        { label: 'Add Product', chip: 'bg-primary-soft text-primary' },
        { label: 'Categories', chip: 'bg-purple-500/15 text-purple-600 dark:text-purple-300' },
        { label: 'Orders', chip: 'bg-success/15 text-success' },
        { label: 'Pending', chip: 'bg-warning/15 text-warning', count: true },
        { label: 'Users', chip: 'bg-orange-500/15 text-orange-500' },
      ].map(({ label, chip, count }) => (
        <Btn
          key={label}
          className={`flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 p-3 sm:p-4 rounded-xl ${chip}`}
        >
          <span className="text-xs sm:text-sm font-medium">{label}</span>
          {count && <Count w="w-6" className="inline-block h-3 align-middle" />}
        </Btn>
      ))}
    </div>
  </div>
);
