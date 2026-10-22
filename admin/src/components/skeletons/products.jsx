// src/components/skeletons/products.jsx
import React from 'react';
import { Plus, Edit, ArrowLeft, Save } from 'lucide-react';
import { Card, Btn, TabHeader, SectionTitle, Count, StaticSearch, HeadRow, MobileRowCards, ListFooter, Skeleton } from './_shared';

export const ProductsSkeleton = () => (
  <div>
    <TabHeader
      title="Products"
      subtitle={(
        <>
          <Count w="w-8" /> products found
        </>
      )}
      actions={(
        <Btn className="btn-primary gap-2 w-full sm:w-auto justify-center py-2.5 sm:py-2">
          <Plus size={20} />
          Add Product
        </Btn>
      )}
    />

    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
      <StaticSearch placeholder="Search products..." />
    </div>

    <Card className="overflow-hidden">
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <HeadRow cols={['checkbox', 'Product', 'Price', 'Status', 'Variants', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 6 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-4 rounded" />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded-lg shrink-0" />
                    <div className="space-y-2">
                      <Skeleton className="h-4 w-40" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-16" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-16 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-10" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-5 w-20 ml-auto" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <MobileRowCards rows={5} thumb />
      <ListFooter />
    </Card>
  </div>
);

export const ProductDetailSkeleton = () => (
  <div className="w-full">
    {/* Header - static back button + Edit Product action; name/slug are dynamic */}
    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div className="flex items-center gap-3">
        <Btn className="text-muted-foreground">
          <ArrowLeft size={20} />
        </Btn>
        <div className="min-w-0">
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-4 w-40 mt-2" />
        </div>
      </div>
      <Btn className="gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg">
        <Edit size={18} />
        Edit Product
      </Btn>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
      <div className="lg:col-span-3 space-y-4">
        <Card className="p-4 sm:p-5">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">Product Information</SectionTitle>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[0, 1, 2, 3].map((n) => (
              <div key={n}>
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-4 w-32 mt-2" />
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-4 sm:p-5">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">Pricing</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-6 w-24 mt-2" />
            </div>
            <div>
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-6 w-24 mt-2" />
            </div>
          </div>
        </Card>

        <Card className="p-4 sm:p-5">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">
            Variants (<Count w="w-6" className="inline-block h-4 align-middle" />)
          </SectionTitle>
          <div className="space-y-3 xl:space-y-0 xl:grid xl:grid-cols-2 xl:gap-3">
            {[0, 1, 2, 3].map((n) => (
              <div
                key={n}
                className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg border border-border"
              >
                <div className="space-y-2">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-40" />
                </div>
                <Skeleton className="h-4 w-20" />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="lg:col-span-2 space-y-4">
        <Card className="p-4 sm:p-5">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">
            Images (<Count w="w-6" className="inline-block h-4 align-middle" />)
          </SectionTitle>
          <div className="grid grid-cols-3 xl:grid-cols-4 gap-2">
            {[0, 1, 2, 3, 4, 5].map((t) => (
              <Skeleton key={t} className="aspect-square w-full rounded-lg" />
            ))}
          </div>
        </Card>
        <Card className="p-4 sm:p-5">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">
            Quick Stats
          </SectionTitle>
          <div className="space-y-2">
            {[0, 1, 2].map((r) => (
              <div key={r} className="flex items-center justify-between gap-3 p-2 bg-muted rounded-lg">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-12" />
              </div>
            ))}
          </div>
        </Card>
        <Card className="p-4 sm:p-5">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">
            Actions
          </SectionTitle>
          <Btn className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg">
            <ArrowLeft size={18} />
            Back to Products
          </Btn>
        </Card>
      </div>
    </div>
  </div>
);

export const ProductFormSkeleton = ({ title = 'Create New Product', mode = 'edit' }) => (
  <div className="pb-8">
    {/* Static header - back button + real title (matches the real page) */}
    <div className="flex flex-wrap items-center gap-3 mb-4">
      <Btn className="text-muted-foreground">
        <ArrowLeft size={20} />
      </Btn>
      <h1 className="text-lg sm:text-xl font-bold text-foreground break-words">{title}</h1>
    </div>

    {/* Create mode is single-column (variants/images unlock after save);
        edit mode is the 3-column info + variants + images layout */}
    <div className={`grid grid-cols-1 gap-4 ${mode === 'create' ? '' : 'lg:grid-cols-3'}`}>
      {/* LEFT - Product Information */}
      <div className={`flex flex-col gap-4 ${mode === 'create' ? 'lg:col-span-3' : 'lg:col-span-1'}`}>
        <Card className="p-4 sm:p-5 flex-1">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">
            Product Information
          </SectionTitle>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">
                Name <span className="text-destructive">*</span>
              </p>
              <Skeleton className="h-9 w-full rounded-lg" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">
                Slug <span className="text-destructive">*</span>
              </p>
              <Skeleton className="h-9 w-full rounded-lg" />
            </div>
          </div>
          <div className="mt-3">
            <p className="text-sm font-medium text-muted-foreground mb-1">Category</p>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
          <div className="mt-3">
            <p className="text-sm font-medium text-muted-foreground mb-1">Description</p>
            <Skeleton className="h-20 w-full rounded-lg" />
          </div>
          <div className="mt-3 pt-3 border-t border-border">
            <p className="text-sm font-medium text-muted-foreground mb-2">Pricing</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">
                  Price <span className="text-destructive">*</span>
                </p>
                <Skeleton className="h-9 w-full rounded-lg" />
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Compare at Price</p>
                <Skeleton className="h-9 w-full rounded-lg" />
              </div>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-border flex items-center gap-4">
            <Skeleton className="h-4 w-4 rounded" />
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
        </Card>

        {/* Actions - helper text + save button (matches the real page) */}
        <Card className="p-3 flex flex-wrap items-center gap-x-4 gap-y-2 justify-end">
          <Skeleton className="h-4 w-48 mr-auto" />
          <Btn className="bg-primary text-primary-foreground px-4 py-1.5 rounded-lg text-sm font-medium gap-2">
            <Save size={16} />
            {mode === 'create' ? 'Create Product' : 'Update Product'}
          </Btn>
        </Card>
      </div>

      {/* MIDDLE - Variants (edit mode only: unlocked after save) */}
      {mode !== 'create' && (
      <div className="flex flex-col gap-4">
        <Card className="p-4 sm:p-5 flex-1 flex flex-col">
          <SectionTitle className="text-base font-semibold text-foreground mb-3">
            Variants (<Count w="w-4" className="inline-block h-4 align-middle" />)
          </SectionTitle>
          <div className="border rounded-lg p-3 mb-3 bg-muted">
            <div className="grid grid-cols-1 gap-3">
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">
                  SKU <span className="text-destructive">*</span>
                </p>
                <Skeleton className="h-9 w-full rounded-lg" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-1">Price Override</p>
                  <Skeleton className="h-9 w-full rounded-lg" />
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-1">Stock</p>
                  <Skeleton className="h-9 w-full rounded-lg" />
                </div>
              </div>
            </div>
            <Skeleton className="h-10 w-full rounded-lg mt-3" />
          </div>
          <div className="space-y-2">
            {[0, 1].map((n) => (
              <div key={n} className="flex items-center justify-between gap-3 bg-muted p-3 rounded-lg border border-border">
                <div className="space-y-2">
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-3 w-40" />
                </div>
                <div className="flex items-center gap-2">
                  <Skeleton className="h-6 w-6 rounded" />
                  <Skeleton className="h-6 w-6 rounded" />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
      )}

      {/* RIGHT - Images (edit mode only: unlocked after save) */}
      {mode !== 'create' && (
      <div className="flex flex-col gap-4">
        <Card className="p-4 sm:p-5 flex-1 flex flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <SectionTitle className="text-base font-semibold text-foreground">
              Images (<Count w="w-4" className="inline-block h-4 align-middle" />)
            </SectionTitle>
          </div>
          <div className="border rounded-lg p-3 mb-3 bg-muted">
            <div className="grid grid-cols-1 gap-3">
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">
                  Image URL <span className="text-destructive">*</span>
                </p>
                <Skeleton className="h-9 w-full rounded-lg" />
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Alt Text</p>
                <Skeleton className="h-9 w-full rounded-lg" />
              </div>
            </div>
            <Skeleton className="h-10 w-full rounded-lg mt-3" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[0, 1, 2, 3].map((t) => (
              <Skeleton key={t} className="aspect-square w-full rounded-lg" />
            ))}
          </div>
        </Card>
      </div>
      )}
    </div>
  </div>
);
