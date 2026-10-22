// src/components/skeletons/store-settings.jsx
import React from 'react';
import { RefreshCw, Save, SlidersHorizontal } from 'lucide-react';
import { Card, Btn, Count, Skeleton } from './_shared';

export const StoreSettingsSkeleton = () => (
  <div>
    <div className="flex flex-wrap justify-between items-center gap-2 mb-4">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2">
          <SlidersHorizontal size={20} className="text-primary shrink-0" />
          Store Settings
        </h1>
        <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
          <Count w="w-48" className="inline-block h-3 align-middle" />
        </p>
      </div>
      <Btn className="px-2.5 py-1.5 border border-input rounded-lg text-xs gap-1">
        <RefreshCw size={13} />
        Refresh
      </Btn>
    </div>

    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-4">
      {[
        { title: 'Tax & pricing', rows: 1 },
        { title: 'Shipping', rows: 2 },
        { title: 'Cash on Delivery', rows: 3 },
        { title: 'Cancellations & refunds', rows: 4 },
        { title: 'Unpaid orders', rows: 1 },
      ].map(({ title, rows }) => (
        <Card key={title} className="p-4">
          <h2 className="text-[15px] font-semibold text-foreground mb-3">{title}</h2>
          <div className="space-y-3">
            {Array.from({ length: rows }).map((_, i) => (
              <div key={i} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <Skeleton className="h-4 w-2/3 sm:w-1/2" />
                <Skeleton className="h-9 w-full sm:w-32 rounded-lg shrink-0" />
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>

    <div className="sticky bottom-0 mt-3 flex justify-end bg-background/95 backdrop-blur py-2.5 border-t border-border">
      <Btn className="px-5 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium gap-2">
        <Save size={16} />
        Save Store Settings
      </Btn>
    </div>
  </div>
);
