import React from 'react';

// ✅ Block skeleton (default). Pass `inline` when the skeleton sits inside a
//    phrasing-content-only element (<p>, <span>, <button>, <label>, …): a <div>
//    there is invalid HTML — the browser hoists it out of its parent, so the
//    loading state breaks the layout of the element it belongs to.
const Skeleton = ({ className = '', inline = false }) =>
  inline ? (
    <span
      className={`animate-pulse rounded-xl bg-muted inline-block align-middle ${className}`}
      aria-hidden="true"
    />
  ) : (
    <div className={`animate-pulse rounded-xl bg-muted ${className}`} aria-hidden="true" />
  );

export const ProductCardSkeleton = () => {
  return (
    <div className="group relative w-full rounded-[2rem] bg-card p-4 border border-border transition-colors duration-700">
      <Skeleton className="absolute top-5 right-5 h-10 w-10 rounded-full z-20" />
      <div className="relative aspect-[4/5] overflow-hidden rounded-2xl bg-primary-soft">
        <Skeleton className="absolute inset-0 rounded-2xl" />
        <div className="absolute top-4 left-4 z-10">
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <div className="absolute bottom-4 left-1/2 w-[90%] -translate-x-1/2">
          <Skeleton className="h-10 w-full rounded-full" />
        </div>
      </div>
      <div className="pt-6 pb-2 px-2">
        <div className="flex justify-between items-start gap-4 mb-2">
          <div className="h-11 min-w-0 flex-1">
            <Skeleton className="h-7 w-11/12" />
          </div>
          <Skeleton className="h-4 w-12 shrink-0 mt-1" />
        </div>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Skeleton className="h-7 w-[45%]" />
          <Skeleton className="h-5 w-[25%]" />
        </div>
        <div className="mt-2">
          <Skeleton className="h-4 w-[35%]" />
        </div>
      </div>
    </div>
  );
};

export const ProductGridSkeleton = ({
  count = 8,
  gridClassName = 'grid grid-cols-1 xs:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-4 md:gap-6',
}) => {
  return (
    <div className={gridClassName}>
      {Array.from({ length: count }).map((_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  );
};

export const ProductDetailSkeleton = () => {
  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-20">
      <div className="w-full max-w-6xl mx-auto px-4 lg:px-8 pt-8">
        <nav className="flex gap-2 items-center mb-8">
          <Skeleton className="h-3 w-10" />
          <Skeleton className="h-3 w-1" />
          <Skeleton className="h-3 w-14" />
          <Skeleton className="h-3 w-1" />
          <Skeleton className="h-3 w-32" />
        </nav>

        <div className="flex flex-col lg:flex-row gap-10 lg:gap-12 items-start">
          <div className="w-full lg:w-1/2 lg:sticky lg:top-24 flex flex-col gap-4">
            <div className="relative w-full aspect-square rounded-[2rem] bg-primary-soft overflow-hidden">
              <Skeleton className="absolute inset-0 rounded-[2rem]" />
            </div>
            <div className="flex gap-3 pb-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-16 flex-shrink-0 rounded-xl" />
              ))}
            </div>
          </div>

          <div className="w-full lg:w-1/2 flex flex-col gap-8 pb-10">
            <div>
              <Skeleton className="h-9 md:h-11 lg:h-12 w-4/5" />
              <div className="flex items-center gap-3 mt-4">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20 underline-offset-4" />
              </div>
            </div>

            <div className="flex items-end gap-3">
              <Skeleton className="h-9 md:h-10 w-36" />
              <Skeleton className="h-5 w-24 mb-1" />
            </div>

            <div className="flex flex-col gap-2.5">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-2/3" />
            </div>

            <div className="border-t border-border pt-8">
              <Skeleton className="h-3 w-24 mb-3" />
              <div className="grid grid-cols-2 gap-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="relative p-4 rounded-2xl border-2 border-border bg-transparent">
                    <Skeleton className="h-4 w-24 mb-2" />
                    <Skeleton className="h-3 w-16" />
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-4">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-12 w-36 rounded-full" />
              </div>
              <Skeleton className="h-14 w-full rounded-full" />
            </div>

            <div className="grid grid-cols-3 gap-3 pt-6 border-t border-border">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="flex flex-col items-center gap-2 p-3 rounded-2xl bg-card border border-border">
                  <Skeleton className="h-8 w-8 rounded-full" />
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-2.5 w-14" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const OrderCardSkeleton = () => {
  return (
    <div className="bg-card rounded-[2rem] border border-border overflow-hidden">
      <div className="flex flex-wrap justify-between items-start gap-3 p-5 sm:p-6 border-b border-border">
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center gap-2.5">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
          <Skeleton className="h-4 w-64 max-w-full" />
        </div>
        <div className="flex flex-col items-start sm:items-end gap-1.5">
          <Skeleton className="h-7 w-28" />
          <Skeleton className="h-3 w-24" />
        </div>
      </div>
      <div className="px-5 sm:px-6 py-4 flex flex-col gap-3">
        <Skeleton className="h-[58px] w-full" />
        <Skeleton className="h-[58px] w-full" />
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 px-5 sm:px-6 py-4 bg-primary-soft/50 border-t border-border">
        <Skeleton className="h-4 w-1/2 min-w-[120px]" />
        <Skeleton className="h-11 w-36 rounded-full" />
      </div>
    </div>
  );
};

export const OrdersListSkeleton = ({ count = 3 }) => {
  return (
    <div className="flex flex-col gap-6 sm:gap-8">
      {Array.from({ length: count }).map((_, i) => (
        <OrderCardSkeleton key={i} />
      ))}
    </div>
  );
};

export const ProfileSkeleton = () => {
  return (
    <>
      {/* Hero */}
      <div className="bg-card border border-border rounded-[2rem] shadow-sm overflow-hidden">
        <Skeleton className="h-28 sm:h-36 w-full rounded-none rounded-t-[2rem]" />
        <div className="px-6 sm:px-10 pb-6 sm:pb-8 -mt-12 sm:-mt-14">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-5 sm:gap-6">
            <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
              <Skeleton className="w-24 h-24 sm:w-28 sm:h-28 rounded-[2rem] ring-4 ring-card shrink-0" />
              <div className="pt-2 sm:pt-0 flex flex-col gap-3 min-w-0">
                <Skeleton className="h-7 sm:h-8 w-48 sm:w-64" />
                <div className="flex flex-wrap items-center gap-2">
                  <Skeleton className="h-7 w-20 rounded-full" />
                  <Skeleton className="h-7 w-40 rounded-full" />
                </div>
              </div>
            </div>
            <Skeleton className="h-12 w-36 rounded-full shrink-0 mt-2 sm:mt-0" />
          </div>

          <div className="mt-7 grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="flex items-center gap-3 sm:gap-4 rounded-2xl border border-border bg-background px-4 sm:px-5 py-4">
                <Skeleton className="w-11 h-11 rounded-xl shrink-0" />
                <div className="flex-1 flex flex-col gap-2">
                  <Skeleton className="h-6 w-12" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Account details */}
      <div className="mt-6 sm:mt-8 bg-card border border-border rounded-[2rem] shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 sm:px-8 py-5 border-b border-border">
          <Skeleton className="h-3 w-36" />
          <Skeleton className="h-3 w-10" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="flex items-center gap-4 px-6 sm:px-8 py-5"
              style={{ borderTop: i > 1 ? '1px solid var(--border)' : undefined }}
            >
              <Skeleton className="w-11 h-11 rounded-2xl shrink-0" />
              <div className="flex-1 flex flex-col gap-2">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-4 w-40" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Quick actions */}
      <div className="mt-6 sm:mt-8">
        <Skeleton className="h-3 w-32 mb-4 sm:mb-5" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 max-w-2xl">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-[2rem] shadow-sm p-5 sm:p-6 flex items-center gap-4">
              <Skeleton className="w-12 h-12 rounded-2xl shrink-0" />
              <div className="flex-1 flex flex-col gap-2">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-3 w-44" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
};

export const OrderDetailSkeleton = () => {
  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8 sm:mb-10 border-b border-border pb-6">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-11 w-40 rounded-full" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
          {/* Left column */}
          <div className="lg:col-span-2 space-y-6">
            {/* Hero: order number + status + timeline */}
            <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-8">
              <div className="flex flex-wrap justify-between items-start gap-4">
                <div className="flex flex-col gap-3">
                  <Skeleton className="h-8 w-48" />
                  <Skeleton className="h-3 w-64 max-w-full" />
                </div>
                <div className="flex items-center gap-3">
                  <Skeleton className="h-9 w-28 rounded-full" />
                  <Skeleton className="h-10 w-32 rounded-full" />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-6">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3 p-4 rounded-2xl border border-border">
                    <Skeleton className="w-9 h-9 rounded-full shrink-0" />
                    <div className="flex-1 flex flex-col gap-2">
                      <Skeleton className="h-3 w-20" />
                      <Skeleton className="h-4 w-32" />
                    </div>
                  </div>
                ))}
              </div>
              <Skeleton className="h-3 w-36 mt-5" />
            </div>

            {/* Items + summary */}
            <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-8">
              <div className="flex items-center justify-between mb-5">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-3 w-14" />
              </div>
              <div className="flex flex-col gap-4">
                {[...Array(2)].map((_, i) => (
                  <div key={i} className="flex items-center gap-4">
                    <Skeleton className="w-16 h-16 rounded-2xl shrink-0" />
                    <div className="flex-1 flex flex-col gap-2">
                      <Skeleton className="h-4 w-2/3" />
                      <Skeleton className="h-3 w-1/3" />
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <Skeleton className="h-4 w-16" />
                      <Skeleton className="h-3 w-12" />
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-t border-border mt-6 pt-6 flex flex-col gap-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-7 w-full" />
              </div>
            </div>
          </div>

          {/* Right column */}
          <div className="space-y-6">
            {/* Payment */}
            <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-6">
              <Skeleton className="h-3 w-24 mb-4" />
              <div className="flex flex-col gap-3">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="flex items-center justify-between gap-3">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-3 w-28" />
                  </div>
                ))}
              </div>
              <Skeleton className="h-11 w-full rounded-full mt-5" />
            </div>

            {/* Shipping address */}
            <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-6">
              <Skeleton className="h-3 w-32 mb-5" />
              <div className="flex flex-col gap-2.5">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Skeleton;