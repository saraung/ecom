// src/components/skeletons/categories.jsx
import React from 'react';
import { Plus, ArrowLeft, Save } from 'lucide-react';
import { Card, Btn, TabHeader, Count, StaticSearch, Skeleton } from './_shared';

export const CategoryTreeRow = ({ level = 0 }) => (
  <div
    className={`flex items-center px-4 py-3 ${level > 0 ? 'border-l-2 border-primary/30 ml-4' : ''}`}
    style={{ paddingLeft: `${16 + level * 24}px` }}
  >
    <div className="w-6 shrink-0">
      <Skeleton className="h-4 w-4 rounded" />
    </div>
    <div className="w-6 shrink-0">
      <Skeleton className="h-4 w-4 rounded" />
    </div>
    <div className="flex-1 min-w-0">
      <Skeleton className={`h-4 ${level === 0 ? 'w-40' : 'w-32'}`} />
      <Skeleton className="h-3 w-52 mt-1.5" />
    </div>
    <div className="flex items-center gap-2 shrink-0">
      <Skeleton className="h-7 w-7 rounded-lg" />
      <Skeleton className="h-7 w-7 rounded-lg" />
      <Skeleton className="h-7 w-7 rounded-lg" />
    </div>
  </div>
);

export const CategoriesSkeleton = () => (
  <div>
    <TabHeader
      title="Categories"
      subtitle={(
        <>
          <Count w="w-8" /> categories found
        </>
      )}
      actions={(
        <>
          <Btn className="px-3 py-2 text-sm text-muted-foreground rounded-lg">Expand All</Btn>
          <Btn className="px-3 py-2 text-sm text-muted-foreground rounded-lg">Collapse All</Btn>
          <Btn className="bg-primary text-primary-foreground px-4 py-2 rounded-lg gap-2">
            <Plus size={20} />
            Add Category
          </Btn>
        </>
      )}
    />

    <StaticSearch placeholder="Search categories..." className="relative w-full max-w-md mb-6" />

    <Card className="overflow-x-auto">
      <div className="divide-y divide-border min-w-140">
        {[0, 1, 1, 0, 1, 0, 1].map((level, i) => (
          <CategoryTreeRow key={i} level={level} />
        ))}
      </div>
    </Card>
  </div>
);

export const CategoryProductsSkeleton = () => (
  <div className="pb-8">
    <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
      <div className="flex items-center gap-4">
        <Btn className="p-2 rounded-lg">
          <ArrowLeft size={20} />
        </Btn>
        <div>
          {/* Category name is dynamic */}
          <Skeleton className="h-7 sm:h-8 w-48" />
          <p className="text-sm text-muted-foreground mt-1">
            <Count w="w-6" /> products in this category
          </p>
        </div>
      </div>
      <Btn className="bg-primary text-primary-foreground px-4 py-2 rounded-lg gap-2">
        <Plus size={20} />
        Add Products
      </Btn>
    </div>

    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="bg-card rounded-lg shadow-sm overflow-hidden">
          <Skeleton className="aspect-square w-full rounded-none" />
          <div className="p-2 space-y-1.5">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  </div>
);

export const CategoryFormSkeleton = ({ title = 'Create New Category' }) => (
  <div className="pb-8">
    {/* Static header - back button + real title (matches the real page) */}
    <div className="flex flex-wrap items-center gap-3 mb-3">
      <Btn className="text-muted-foreground">
        <ArrowLeft size={18} />
      </Btn>
      <h1 className="text-lg font-bold text-foreground">{title}</h1>
    </div>

    <div className="space-y-6">
      <Card className="p-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Name */}
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">
              Name <span className="text-destructive">*</span>
            </p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
          {/* Slug */}
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">
              Slug <span className="text-destructive">*</span>
            </p>
            <Skeleton className="h-9 w-full rounded-lg" />
            <p className="text-xs text-muted-foreground mt-1">
              Auto-generated from name
            </p>
          </div>
          {/* Parent Category */}
          <div className="md:col-span-2">
            <p className="text-sm font-medium text-muted-foreground mb-1">
              Parent Category
            </p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
        </div>
      </Card>

      {/* Actions - right-aligned Cancel + Save (matches the real page) */}
      <Card className="p-3 flex flex-wrap items-center gap-x-4 gap-y-2 justify-end">
        <Btn className="px-4 py-1.5 border border-input rounded-lg text-sm font-medium">
          Cancel
        </Btn>
        <Btn className="bg-primary text-primary-foreground px-4 py-1.5 rounded-lg text-sm font-medium gap-2">
          <Save size={16} />
          {title.startsWith('Edit') ? 'Update Category' : 'Create Category'}
        </Btn>
      </Card>
    </div>
  </div>
);
