// src/components/skeletons/promotions.jsx
import React from 'react';
import { RefreshCw, Users, Megaphone } from 'lucide-react';
import { Card, Btn, Skeleton } from './_shared';

export const PromotionsSkeleton = () => (
  <div>
    <div className="mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2 break-words">
          <Megaphone size={24} className="text-primary shrink-0" />
          Promotions
        </h1>
      <p className="text-sm text-muted-foreground mt-1">
        Broadcast promotional messages to every user — they appear instantly in the
        notification bell on their app header.
      </p>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
      {/* Compose form - static labels */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">New Promotion</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Title *</label>
            <Skeleton className="h-10 w-full rounded-lg" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Message *</label>
            <Skeleton className="h-32 w-full rounded-lg" />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">
              Deep link <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <Skeleton className="h-10 w-full rounded-lg" />
            <p className="text-xs text-muted-foreground mt-1">
              Screen in the user app that opens when the notification is tapped.
            </p>
          </div>

          {/* Live preview */}
          <div className="border border-border rounded-lg p-4 bg-muted/50">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Preview (user notification)
            </p>
            <div className="flex items-start gap-3">
              <span className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 bg-warning/20 text-warning">
                <Megaphone size={17} />
              </span>
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-56" />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Users size={14} />
              Recipients: all users
            </span>
            <Btn className="btn-primary gap-2">Send to All Users</Btn>
          </div>
        </div>
      </Card>

      {/* Sent history */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">Sent Promotions</h2>
          <Btn className="p-1.5 rounded" title="Refresh history">
            <RefreshCw size={16} className="text-muted-foreground" />
          </Btn>
        </div>
        <div className="space-y-3">
          {[0, 1, 2, 3].map((n) => (
            <div key={n} className="border border-border rounded-lg p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1 space-y-2">
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-3 w-full" />
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Skeleton className="h-6 w-12 rounded-full" />
                  <Skeleton className="h-7 w-7 rounded" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  </div>
);
