// src/components/skeletons/audit.jsx
import React from 'react';
import { Filter, RefreshCw, ChevronDown } from 'lucide-react';
import { Card, Btn, TabHeader, Count, HeadRow, ListFooter, Skeleton } from './_shared';

export const AuditLogSkeleton = () => (
  <div>
    <TabHeader
      title="Audit Log"
      subtitle={(
        <>
          <Count w="w-8" /> entries — newest first
        </>
      )}
      actions={(
        <>
          <Btn className="gap-2 px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted transition-colors">
            <Filter size={16} />
            <span>Entity</span>
            <ChevronDown size={16} />
          </Btn>
          <Btn className="gap-1 px-3 py-2 border border-input rounded-lg text-sm hover:bg-muted transition-colors">
            <RefreshCw size={15} />
            Refresh
          </Btn>
        </>
      )}
    />

    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px]">
          <HeadRow cols={['', 'Time', 'Actor', 'Action', 'Entity', 'IP']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 8 }).map((_, i) => (
              <tr key={i}>
                <td className="pl-3 pr-0 py-3 w-8">
                  <Skeleton className="h-4 w-4" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-24" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-36" />
                  <Skeleton className="h-3 w-48 mt-1.5" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-3 w-20 mt-1.5" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-3 w-28 mt-1.5" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-24" />
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
