// src/components/skeletons/shipping.jsx
import React from 'react';
import { Truck } from 'lucide-react';
import { Card, Skeleton } from './_shared';

export const ShippingSimulatorSkeleton = () => (
  <div className="space-y-5">
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2">
          <Truck size={20} className="text-primary shrink-0" />
          Shiprocket Simulator
          <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-500/15 text-purple-600">
            Test only
          </span>
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Fire tracking events at a shipment and watch the timeline move.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 w-full sm:w-auto">
        <Skeleton className="h-10 sm:h-9 w-full sm:w-52 rounded-lg" />
        <Skeleton className="h-10 sm:h-9 w-full sm:w-24 rounded-lg" />
      </div>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <Card key={i} className="p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-[86px] w-full rounded-lg" />
          <div className="space-y-2.5 pt-1 border-t border-border/60">
            <Skeleton className="h-3 w-20" />
            <div className="flex flex-wrap gap-2">
              <Skeleton className="h-7 w-24 rounded-lg" />
              <Skeleton className="h-7 w-28 rounded-lg" />
              <Skeleton className="h-7 w-20 rounded-lg" />
            </div>
          </div>
        </Card>
      ))}
    </div>
  </div>
);
