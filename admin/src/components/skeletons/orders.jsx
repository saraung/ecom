// src/components/skeletons/orders.jsx
import React from 'react';
import { Filter, ChevronDown, Package, ArrowLeft, Truck, Printer } from 'lucide-react';
import { Card, Btn, TabHeader, SectionTitle, Count, StaticSearch, HeadRow, MobileRowCards, ListFooter, Skeleton } from './_shared';

export const OrdersSkeleton = () => (
  <div>
    <TabHeader
      title="Orders"
      subtitle={(
        <>
          <Count w="w-8" /> orders found
        </>
      )}
      actions={(
        <Btn className="btn-outline text-sm">Export</Btn>
      )}
    />

    <div className="flex flex-col sm:flex-row gap-2 sm:gap-4 mb-6">
      <StaticSearch placeholder="Search orders by #ID or customer name..." />
      <div className="flex gap-2">
        <Btn className="gap-2 px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors justify-center text-sm">
          <Filter size={18} />
          <span>Status</span>
          <ChevronDown size={16} />
        </Btn>
      </div>
    </div>

    <Card className="overflow-hidden">
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <HeadRow cols={['Order', 'Customer', 'Total', 'Status', 'Payment', 'Date', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 7 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-3 w-12 mt-1.5" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-40 mt-1.5" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-16" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-20 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-16 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-20" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-5 w-20 ml-auto" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <MobileRowCards rows={5} />
      <ListFooter />
    </Card>
  </div>
);

export const OrderDetailSkeleton = () => (
  <div>
    {/* Header - static back button + status badge; order no/date are dynamic */}
    <div className="flex flex-wrap items-center gap-4 mb-6">
      <Btn className="text-muted-foreground">
        <ArrowLeft size={24} />
      </Btn>
      <div className="flex-1 min-w-0">
        <h1 className="text-lg sm:text-2xl font-bold text-foreground break-all">
          Order #<Count w="w-24" className="inline-block h-5 sm:h-6 align-middle" />
        </h1>
        <p className="text-xs sm:text-sm text-muted-foreground">
          Placed on <Count w="w-32" className="inline-block h-4 align-middle" />
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <Skeleton className="h-7 w-24 rounded-full" />
      </div>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        {/* Update Status - static title + status option buttons (manager+) */}
        <Card className="p-6">
          <SectionTitle className="text-lg font-semibold text-foreground mb-4">Update Status</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded'].map((s) => (
              <Skeleton key={s} className="h-9 w-24 rounded-lg" />
            ))}
          </div>
        </Card>

        {/* Order Items */}
        <Card className="p-6">
          <SectionTitle className="text-lg font-semibold text-foreground mb-4">Order Items</SectionTitle>
          <div className="divide-y divide-border">
            {[0, 1, 2].map((r) => (
              <div key={r} className="flex items-start gap-4 py-4 first:pt-0">
                <Skeleton className="h-16 w-16 rounded-lg border border-border shrink-0" />
                <div className="flex-1 space-y-2 min-w-0">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-24" />
                </div>
                <div className="text-right space-y-2 shrink-0">
                  <Skeleton className="h-4 w-16 ml-auto" />
                  <Skeleton className="h-3 w-12 ml-auto" />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-4 border-t border-border space-y-1">
            <div className="flex items-center justify-between">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-16" />
            </div>
            <div className="flex items-center justify-between mt-2 pt-2 border-t border-border">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-5 w-20" />
            </div>
          </div>
        </Card>
      </div>

      <div className="space-y-6">
        {['Customer', 'Shipping Address', 'Payment'].map((title) => (
          <Card key={title} className="p-6">
            <SectionTitle className="text-lg font-semibold text-foreground mb-4">{title}</SectionTitle>
            <div className="space-y-3">
              {[0, 1, 2].map((r) => (
                <div key={r} className="flex items-center justify-between gap-3">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-4 w-24" />
                </div>
              ))}
            </div>
          </Card>
        ))}
        {/* Shiprocket Logistics - Tracker card (matches the real page) */}
        <Card className="p-6">
          <SectionTitle className="text-lg font-semibold text-foreground mb-4">
            <Truck size={18} className="text-primary" />
            Shiprocket Logistics
          </SectionTitle>
          <div className="space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-56 font-mono" />
          </div>
          <Skeleton className="h-[86px] w-full rounded-lg mt-3" />
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Skeleton className="h-8 w-full rounded-lg" />
            <Skeleton className="h-8 w-full rounded-lg" />
          </div>
        </Card>
        {/* Actions - full-width buttons (matches the real page) */}
        <Card className="p-6">
          <SectionTitle className="text-lg font-semibold text-foreground mb-4">Actions</SectionTitle>
          <div className="space-y-2">
            <Btn className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg">
              <Package size={18} />
              Print Packing Slip
            </Btn>
            <Btn className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg">
              <Printer size={18} />
              Print Invoice
            </Btn>
          </div>
        </Card>
      </div>
    </div>
  </div>
);
