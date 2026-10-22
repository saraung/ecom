// src/components/skeletons/mcp-agent.jsx
import React from 'react';
import { Skeleton } from './_shared';

export const McpAgentSkeleton = () => (
  <div>
    <div className="mb-6 min-w-0 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold text-foreground break-words">MCP Agent</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Ask questions and administer your ecommerce data — orders, products, customers and more.
        </p>
        <div className="mt-2 flex gap-2">
          <Skeleton className="h-8 w-24 rounded-lg" />
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
      </div>
      <Skeleton className="h-6 w-16 rounded-full shrink-0" />
    </div>

    <div className="flex flex-col lg:flex-row gap-4 items-start">
      {/* Thread list renders only when the History toggle is open
          (closed by default), so the skeleton matches the default view. */}
      <div className="flex-1 min-w-0 w-full bg-card border border-border rounded-lg overflow-hidden">
        <div className="p-4 space-y-3">
          <div className="flex justify-start">
            <div className="max-w-[80%] w-2/3">
              <Skeleton className="h-4 w-full rounded-2xl rounded-bl-md" />
              <Skeleton className="h-4 w-4/5 rounded-2xl rounded-bl-md mt-1.5" />
            </div>
          </div>
          <div className="flex justify-end">
            <Skeleton className="h-9 w-40 max-w-[80%] rounded-2xl rounded-br-md" />
          </div>
          <div className="flex justify-start">
            <div className="max-w-[80%] w-1/2">
              <Skeleton className="h-4 w-full rounded-2xl rounded-bl-md" />
              <Skeleton className="h-4 w-3/5 rounded-2xl rounded-bl-md mt-1.5" />
            </div>
          </div>
          <div className="flex gap-2 overflow-hidden">
            <Skeleton className="h-7 w-40 rounded-full shrink-0" />
            <Skeleton className="h-7 w-48 rounded-full shrink-0" />
            <Skeleton className="h-7 w-32 rounded-full shrink-0" />
          </div>
        </div>
        <div className="border-t border-border p-3 flex items-center gap-2">
          <Skeleton className="h-11 flex-1 rounded-lg" />
          <Skeleton className="h-11 w-20 rounded-lg shrink-0" />
        </div>
      </div>
    </div>
  </div>
);
