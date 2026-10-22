// src/components/skeletons/content.jsx
import React from 'react';
import { Plus, RefreshCw, ArrowLeft, Megaphone, Save, Images } from 'lucide-react';
import { Card, Btn, HeadRow, Skeleton } from './_shared';

export const BannersSkeleton = () => (
  <div>
    {/* Mirrors Content.jsx header exactly: same size, same Images icon, same
        actions — so nothing shifts when the real header loads. */}
    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2 break-words">
          <Images size={22} className="text-primary shrink-0" />
          Banners
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Announcement bar, homepage hero and promo banners — no deploy needed
        </p>
      </div>
      <div className="flex flex-col sm:flex-row w-full sm:w-auto gap-2">
        <Btn className="gap-1 px-3 py-2.5 sm:py-2 border border-input rounded-lg text-sm justify-center">
          <RefreshCw size={15} />
          Refresh
        </Btn>
        <Btn className="gap-1 px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg text-sm justify-center">
          <Plus size={15} />
          New block
        </Btn>
      </div>
    </div>
    <Card className="p-4 mb-6">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
        Live slots
      </p>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-6 w-36 rounded-full" />
        <Skeleton className="h-6 w-28 rounded-full" />
      </div>
    </Card>

    <Card className="overflow-hidden">
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full min-w-[760px]">
          <HeadRow cols={['Slot', 'Title', 'Window', 'State', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 5 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-32 font-mono" />
                </td>
                <td className="px-4 py-3 max-w-[260px]">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-56 mt-1.5" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-36" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-16 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-1 justify-end">
                    <Skeleton className="h-7 w-7 rounded" />
                    <Skeleton className="h-7 w-7 rounded" />
                    <Skeleton className="h-7 w-7 rounded" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="md:hidden divide-y divide-border">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-6 w-16 rounded-full shrink-0" />
            </div>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-1/2" />
            <div className="flex gap-2 pt-1">
              <Skeleton className="h-10 flex-1 rounded-lg" />
              <Skeleton className="h-10 flex-1 rounded-lg" />
              <Skeleton className="h-10 w-12 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    </Card>
  </div>
);

export const ContentFormSkeleton = ({ title = 'New Banner' }) => (
  <div>
    <Btn className="flex items-center gap-1 text-sm text-muted-foreground mb-3">
      <ArrowLeft size={15} />
      Back to Banners
    </Btn>
    <div className="flex flex-wrap items-end justify-between gap-2 mb-4">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">{title}</h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Pick a slot, compose, schedule — live on save.
        </p>
      </div>
      <div className="flex gap-2 w-full sm:w-auto">
        <Btn className="flex-1 sm:flex-none px-4 py-2 border border-input rounded-lg text-sm justify-center">
          Cancel
        </Btn>
        <Btn className="flex-1 sm:flex-none px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium gap-1 justify-center">
          <Save size={15} />
          {title.startsWith('Edit') ? 'Save changes' : 'Create banner'}
        </Btn>
      </div>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 items-start">
      <Card className="p-4 space-y-3 lg:col-span-1">
        <h2 className="text-sm font-semibold text-foreground">Compose</h2>
        {['Slot key', 'Title', 'Body'].map((label) => (
          <div key={label}>
            <p className="text-sm font-medium text-muted-foreground mb-1">{label}</p>
            <Skeleton className={`w-full rounded-lg ${label === 'Body' ? 'h-16' : 'h-9'}`} />
          </div>
        ))}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">Link</p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">Link label</p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">Order in slot</p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
          <div className="flex items-end pb-2">
            <Skeleton className="h-5 w-20 rounded" />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">Publish from</p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">Expires at</p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
        </div>
      </Card>

      <Card className="p-4 space-y-3 lg:col-span-1">
        <h2 className="text-sm font-semibold text-foreground">Image (optional)</h2>
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-9 w-full rounded-lg" />
        <Skeleton className="h-36 w-full rounded-lg" />
      </Card>

      <Card className="p-4 lg:col-span-1">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
          Preview
        </p>
        <div className="flex items-start gap-3">
          <span className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 bg-warning/20 text-warning">
            <Megaphone size={17} />
          </span>
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-full" />
          </div>
        </div>
        <div className="mt-3 space-y-2">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-20" />
        </div>
      </Card>
    </div>
  </div>
);
