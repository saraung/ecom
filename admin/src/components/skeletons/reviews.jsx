// src/components/skeletons/reviews.jsx
import React from 'react';
import { Search, RefreshCw, ChevronDown, Star, Eye } from 'lucide-react';
import { Card, Btn, TabHeader, Count, HeadRow, ListFooter, Skeleton } from './_shared';

export const ReviewsSkeleton = () => (
  <div>
    <TabHeader
      title="Reviews"
      subtitle={(
        <>
          <Count w="w-8" /> reviews — hidden ones stay on record, off the storefront
        </>
      )}
      actions={(
        <Btn className="gap-1 px-3 py-2 border border-input rounded-lg text-sm">
          <RefreshCw size={15} />
          Refresh
        </Btn>
      )}
    />

    <div className="flex flex-col sm:flex-row gap-2 mb-6">
      <div className="relative flex-1">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          readOnly
          tabIndex={-1}
          placeholder="Search title, comment, author email…"
          className="w-full pl-9 pr-3 py-2 border border-input rounded-lg text-sm bg-card text-foreground focus:outline-none"
        />
      </div>
      <div className="grid grid-cols-2 sm:flex gap-2">
        <Btn className="gap-1 px-3 py-2.5 sm:py-2 border border-input rounded-lg text-sm justify-center">
          <Star size={15} />
          <span>All ratings</span>
          <ChevronDown size={14} />
        </Btn>
        <Btn className="gap-1 px-3 py-2.5 sm:py-2 border border-input rounded-lg text-sm justify-center">
          <Eye size={15} />
          <span>All + hidden</span>
          <ChevronDown size={14} />
        </Btn>
      </div>
    </div>

    <Card className="overflow-hidden">
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full min-w-[820px]">
          <HeadRow cols={['Rating', 'Review', 'Product', 'Author', 'Date', 'State', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 6 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-0.5">
                    {[0, 1, 2, 3, 4].map((s) => (
                      <Skeleton key={s} className="h-3 w-3 rounded-full" />
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3 max-w-[280px]">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-56 mt-1.5" />
                  <div className="flex items-center gap-1.5 mt-1.5">
                    <Skeleton className="h-10 w-10 rounded-lg" />
                    <Skeleton className="h-10 w-10 rounded-lg" />
                    <Skeleton className="h-10 w-10 rounded-lg" />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-24" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-28" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-20" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-16 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2 justify-end">
                    <Skeleton className="h-7 w-[72px] rounded-lg" />
                    <Skeleton className="h-7 w-[72px] rounded-lg" />
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
              <div className="flex items-center gap-0.5">
                {[0, 1, 2, 3, 4].map((s) => (
                  <Skeleton key={s} className="h-3 w-3 rounded-full" />
                ))}
              </div>
              <Skeleton className="h-6 w-16 rounded-full shrink-0" />
            </div>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-full" />
            <div className="flex items-center gap-1.5">
              <Skeleton className="h-14 w-14 rounded-xl" />
              <Skeleton className="h-14 w-14 rounded-xl" />
              <Skeleton className="h-14 w-14 rounded-xl" />
            </div>
            <Skeleton className="h-3 w-1/2" />
            <div className="flex gap-2 pt-1">
              <Skeleton className="h-10 flex-1 rounded-lg" />
              <Skeleton className="h-10 flex-1 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
      <ListFooter />
    </Card>
  </div>
);
