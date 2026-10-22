// src/components/skeletons/invites.jsx
import React from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { Card, Btn, TabHeader, HeadRow, Skeleton } from './_shared';

export const InvitesSkeleton = () => (
  <div>
    <TabHeader
      title="Staff Invites"
      subtitle="invite by email — the link expires in 7 days and works once"
      actions={(
        <Btn className="gap-1 px-3 py-2 border border-input rounded-lg text-sm hover:bg-muted transition-colors">
          <RefreshCw size={15} />
          Refresh
        </Btn>
      )}
    />

    <Card className="p-4 mb-6">
      <div className="flex flex-col md:flex-row gap-3">
        <div className="flex-1">
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
        <Btn className="gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium justify-center">
          <Plus size={15} />
          Send invite
        </Btn>
      </div>

      <div className="mt-4">
        <Skeleton className="h-3 w-12" />
        <div className="flex flex-wrap gap-2 mt-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-7 w-24 rounded-full" />
          ))}
        </div>
        <Skeleton className="h-3 w-2/3 mt-3" />
      </div>
    </Card>

    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px]">
          <HeadRow cols={['Email', 'Roles', 'Status', 'Expires', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 4 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-44" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-28" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-20 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-24" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-32 ml-auto" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  </div>
);
