// src/components/skeletons/roles.jsx
import React from 'react';
import { Plus, ArrowLeft, Save } from 'lucide-react';
import { Card, Btn, TabHeader, Skeleton } from './_shared';
import { currencySymbol } from '../../utils/format';

export const RolesSkeleton = () => (
  <div>
    <TabHeader
      title="Roles"
      subtitle="permissions are assigned per role"
      actions={(
        <Btn className="flex items-center justify-center gap-2 px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
          <Plus size={18} />
          New Role
        </Btn>
      )}
    />

    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <Card key={i} className="p-5 flex flex-col gap-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <Skeleton className="h-4 w-4 rounded shrink-0" />
              <Skeleton className="h-5 w-32" />
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <Skeleton className="h-7 w-7 rounded" />
              <Skeleton className="h-7 w-7 rounded" />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Skeleton className="h-5 w-20 rounded-full" />
            <Skeleton className="h-5 w-14 rounded-full" />
            <Skeleton className="h-4 w-16" />
          </div>
          <Skeleton className="h-4 w-full" />
          <div className="flex flex-wrap gap-1.5 mt-auto">
            <Skeleton className="h-5 w-24 rounded-full" />
            <Skeleton className="h-5 w-28 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
        </Card>
      ))}
    </div>
  </div>
);

export const RoleFormSkeleton = ({ title = 'Create New Role' }) => (
  <div className="pb-8">
    <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-3">
      <Btn className="text-muted-foreground">
        <ArrowLeft size={18} />
      </Btn>
      <h1 className="text-lg font-bold text-foreground break-words min-w-0 flex-1 basis-40">
        {title}
        {/* Edit mode appends " — {name}": reserve the space so the
            title doesn't grow once the role loads. */}
        {title.startsWith('Edit') && (
          <span className="font-bold">
            {' — '}
            <Skeleton className="h-5 w-32 inline-block align-middle rounded" />
          </span>
        )}
      </h1>
    </div>

    <div className="space-y-6">
      <Card className="p-4 sm:p-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">
              Name <span className="text-destructive">*</span>
            </p>
            <Skeleton className="h-10 w-full rounded-lg" />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">Slug</p>
            <Skeleton className="h-10 w-full rounded-lg" />
          </div>
          <div className="md:col-span-2">
            <p className="text-sm font-medium text-muted-foreground mb-1">Description</p>
            <Skeleton className="h-10 w-full rounded-lg" />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">
              Max auto-refund ({currencySymbol()}) — blank = unlimited
            </p>
            <Skeleton className="h-10 w-full rounded-lg" />
            <Skeleton className="h-3 w-2/3 mt-1.5 rounded" />
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-16" />
        </div>
        <div className="space-y-5">
          {[0, 1].map((g) => (
            <div key={g} className="border border-border rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-4 w-20" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {[0, 1, 2, 3, 4, 5].map((p) => (
                  <Skeleton key={p} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-3 flex flex-wrap items-center gap-x-4 gap-y-2 justify-end">
        <Btn className="px-4 py-1.5 border border-input rounded-lg text-sm font-medium">
          Cancel
        </Btn>
          <Btn className="bg-primary text-primary-foreground px-4 py-1.5 rounded-lg text-sm font-medium gap-2">
            <Save size={16} />
            {title.startsWith('Edit') ? 'Update Role' : 'Create Role'}
          </Btn>
      </Card>
    </div>
  </div>
);
