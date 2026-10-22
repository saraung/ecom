// src/components/skeletons/refunds.jsx
import React from 'react';
import { Card, Btn, TabHeader, HeadRow, ListFooter, Skeleton } from './_shared';

export const RefundsSkeleton = () => (
  <div>
    <TabHeader
      title="Refunds"
      subtitle="pending rows need a second admin"
      actions={(
        <Btn className="px-3 py-2 border border-input rounded-lg text-sm">
          Refresh
        </Btn>
      )}
    />

    <div className="flex gap-2 border-b border-border overflow-x-auto mb-6">
      <Skeleton className="h-9 w-32 rounded-none" />
      <Skeleton className="h-9 w-24 rounded-none" />
    </div>

    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px]">
          <HeadRow cols={['Order', 'Amount', 'Status', 'Requested by', 'Reason', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 6 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-24" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-16" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-24 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-32" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-40" />
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2 justify-end">
                    <Skeleton className="h-7 w-20 rounded" />
                    <Skeleton className="h-7 w-16 rounded" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ListFooter />
    </Card>
  </div>
);
