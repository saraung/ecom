// src/components/skeletons/returns.jsx
import React from 'react';
import { RefreshCw, PackageOpen, ArrowLeft } from 'lucide-react';
import { Card, Btn, SectionTitle, Count, HeadRow, ListFooter, Skeleton } from './_shared';

export const ReturnListSkeleton = () => (
  <div className="space-y-6">
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-3"><PackageOpen size={26} /> Product returns</h1>
        <p className="text-sm text-muted-foreground mt-1">Review delivered-item returns, receipt, inspection and refunds.</p>
      </div>
      <Btn className="gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium"><RefreshCw size={16} /> Refresh</Btn>
    </div>
    <Card className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      {[0, 1, 2].map((index) => <div key={index} className="space-y-1"><Skeleton className="h-3 w-20" /><Skeleton className="h-10 w-full rounded-lg" /></div>)}
      <div className="flex items-end gap-2"><Skeleton className="h-9 w-28 rounded-lg" /><Skeleton className="h-9 w-24 rounded-lg" /></div>
    </Card>
    <Card className="overflow-hidden">
      <div className="hidden md:block overflow-x-auto"><table className="w-full text-sm"><HeadRow cols={['Return / order', 'Customer', 'Items / reason', 'Refund', 'Status', 'Requested', '']} /><tbody className="divide-y divide-border">
        {Array.from({ length: 6 }).map((_, index) => <tr key={index}><td className="p-4"><Skeleton className="h-4 w-28" /><Skeleton className="h-3 w-24 mt-2" /></td><td className="p-4"><Skeleton className="h-4 w-32" /><Skeleton className="h-3 w-40 mt-2" /></td><td className="p-4"><Skeleton className="h-4 w-16" /><Skeleton className="h-3 w-28 mt-2" /></td><td className="p-4"><Skeleton className="h-4 w-16" /></td><td className="p-4"><Skeleton className="h-6 w-24 rounded-full" /></td><td className="p-4"><Skeleton className="h-3 w-20" /></td><td className="p-4"><Skeleton className="h-8 w-20 ml-auto rounded-lg" /></td></tr>)}
      </tbody></table></div>
      <div className="md:hidden divide-y divide-border">{Array.from({ length: 5 }).map((_, index) => <div key={index} className="p-4 space-y-3"><div className="flex justify-between gap-3"><Skeleton className="h-4 w-28" /><Skeleton className="h-6 w-24 rounded-full" /></div><Skeleton className="h-4 w-48" /><Skeleton className="h-3 w-40" /><div className="flex justify-between"><Skeleton className="h-4 w-28" /><Skeleton className="h-4 w-16" /></div><Skeleton className="h-3 w-24" /></div>)}</div>
      <ListFooter />
    </Card>
  </div>
);

export const ReturnDetailSkeleton = () => (
  <div className="space-y-6">
    <div className="flex items-center justify-between gap-4"><Btn className="gap-2 rounded-lg border border-border px-4 py-2 text-sm font-semibold"><ArrowLeft size={17} /> Returns</Btn><Btn className="gap-2 rounded-lg border border-border px-4 py-2 text-sm font-semibold"><RefreshCw size={17} /> Refresh</Btn></div>
    <Card className="p-4 sm:p-6"><div className="flex flex-wrap justify-between gap-4"><div><h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-3"><PackageOpen size={25} /> <Skeleton className="h-7 w-40" /></h1><Skeleton className="h-4 w-56 mt-3" /></div><Skeleton className="h-9 w-28 rounded-full" /></div><div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mt-6">{Array.from({ length: 7 }).map((_, index) => <div key={index} className="rounded-lg p-3 border border-border bg-muted/30"><Skeleton className="h-3 w-20" /><Skeleton className="h-3 w-24 mt-2" /></div>)}</div></Card>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start"><div className="lg:col-span-2 space-y-6"><Card className="p-4 sm:p-6"><SectionTitle>Returned items</SectionTitle><div className="divide-y divide-border mt-4">{[0, 1].map((index) => <div key={index} className="py-3 flex justify-between gap-4"><div className="space-y-2"><Skeleton className="h-4 w-44" /><Skeleton className="h-3 w-32" /><Skeleton className="h-3 w-52" /></div><Skeleton className="h-4 w-16" /></div>)}</div><Skeleton className="h-20 w-full mt-4" /></Card><Card className="p-4 sm:p-6"><SectionTitle>Evidence photos <Count w="w-6" /></SectionTitle><Skeleton className="h-3 w-64 mt-2" /><div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">{[0, 1, 2].map((index) => <Skeleton key={index} className="aspect-square w-full rounded-lg" />)}</div></Card><Card className="p-4 sm:p-6"><SectionTitle>Status and activity history</SectionTitle><div className="space-y-5 border-l border-border ml-2 pl-5 mt-5">{[0, 1, 2, 3].map((index) => <div key={index} className="space-y-2"><Skeleton className="h-4 w-44" /><Skeleton className="h-3 w-28" /><Skeleton className="h-3 w-64" /></div>)}</div></Card></div><aside className="space-y-6">{['Customer', 'Refund', 'Return shipping'].map((title) => <Card key={title} className="p-4 sm:p-6"><SectionTitle>{title}</SectionTitle><div className="space-y-3 mt-4"><Skeleton className="h-5 w-40" /><Skeleton className="h-4 w-56" /><Skeleton className="h-4 w-32" /></div></Card>)}</aside></div>
  </div>
);
