// src/components/skeletons/cod.jsx
import React from 'react';
import { Plus, RefreshCw, Download, Banknote, FileUp, FlaskConical, ShieldAlert, Trash2, XCircle, ArrowLeft, Save } from 'lucide-react';
import { Card, Btn, SectionTitle, Count, StaticSearch, HeadRow, Skeleton } from './_shared';

export const CodSummaryCardsSkeleton = ({
  count = 5,
  cols = 'grid-cols-2 lg:grid-cols-5',
  className = 'mb-6',
}) => (
  <div className={`grid ${cols} gap-3 ${className}`}>
    {Array.from({ length: count }).map((_, index) => (
      <Card key={index} className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-7 w-20" />
            <Skeleton className="h-3 w-28" />
          </div>
          <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
        </div>
      </Card>
    ))}
  </div>
);

export const CodReconciliationSkeleton = () => (
  <div>
    <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3 mb-6">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground">COD Reconciliation</h1>
        <p className="text-sm text-muted-foreground">
          Customer cash collection and courier remittance are tracked separately — remittance never creates a payment.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full sm:flex sm:flex-wrap sm:items-center lg:w-auto">
        <Btn className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-input rounded-lg text-xs sm:text-sm gap-1.5">
          <Download size={15} /> Template
        </Btn>
        <Btn className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-input rounded-lg text-xs sm:text-sm gap-1.5">
          <FlaskConical size={15} />
          <span className="sm:hidden">Fixture</span>
          <span className="hidden sm:inline">Synthetic fixture</span>
        </Btn>
        <Btn className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 bg-primary text-primary-foreground rounded-lg text-xs sm:text-sm font-medium gap-1.5">
          <FileUp size={15} />
          <span className="sm:hidden">Import</span>
          <span className="hidden sm:inline">Import CSV</span>
        </Btn>
        <Btn className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-input rounded-lg text-xs sm:text-sm gap-1.5">
          <Plus size={15} />
          <span className="sm:hidden">Manual</span>
          <span className="hidden sm:inline">Manual batch</span>
        </Btn>
        <Btn className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-warning/40 text-warning rounded-lg text-xs sm:text-sm gap-1.5">
          <FlaskConical size={15} />
          <span className="sm:hidden">Simulate</span>
          <span className="hidden sm:inline">Simulate (synthetic)</span>
        </Btn>
        <Btn className="justify-self-end sm:justify-self-auto h-10 w-10 shrink-0 justify-center rounded-full border border-input text-muted-foreground">
          <RefreshCw size={16} />
        </Btn>
      </div>
    </div>

    <CodSummaryCardsSkeleton />

    <div className="mb-4 rounded-lg border border-border bg-muted/20 px-4 py-3 space-y-2">
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>

    <div className="flex gap-2 border-b border-border overflow-x-auto mb-6">
      <div className="px-4 py-2 text-sm font-medium border-b-2 border-primary text-primary whitespace-nowrap inline-flex items-center gap-1.5">
        Remittance batches <Count w="w-8" />
      </div>
      <div className="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-muted-foreground whitespace-nowrap inline-flex items-center gap-1.5">
        Cash collection <Count w="w-6" />
      </div>
    </div>

    <div className="flex flex-col sm:flex-row gap-2 mb-4">
      <StaticSearch placeholder="Search CRF or UTR…" className="relative w-full sm:max-w-sm" />
      <Skeleton className="h-10 w-full sm:w-44 rounded-lg" />
    </div>

    <Card className="overflow-hidden">
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full min-w-[900px]">
          <HeadRow cols={['CRF / batch', 'Date', 'Status', 'Gross COD', 'Deductions', 'Net expected', 'Bank credit', 'Lines', '']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 5 }).map((_, index) => (
              <tr key={index}>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-4 w-24 rounded-full mt-2" />
                </td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                <td className="px-4 py-3"><Skeleton className="h-6 w-24 rounded-full" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-16" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-14" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-3 w-24 mt-1.5" />
                </td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-8" /></td>
                <td className="px-4 py-3 text-right"><Skeleton className="h-7 w-16 rounded-lg ml-auto" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="md:hidden divide-y divide-border">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-24 rounded-full" />
              </div>
              <Skeleton className="h-6 w-24 rounded-full shrink-0" />
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2">
              {Array.from({ length: 6 }).map((__, field) => (
                <div key={field} className="space-y-1">
                  <Skeleton className="h-3 w-14" />
                  <Skeleton className="h-4 w-20" />
                </div>
              ))}
            </div>
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
        ))}
      </div>

      <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-1 text-sm text-muted-foreground">
          Page <Count w="w-5" /> of <Count w="w-5" /> · <Count w="w-8" /> batches
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-8 flex-1 sm:flex-none w-20 rounded-lg" />
          <Skeleton className="h-8 flex-1 sm:flex-none w-14 rounded-lg" />
        </div>
      </div>
    </Card>
  </div>
);

export const CodDetailSkeleton = () => (
  <div className="space-y-5">
    <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3">
      <div className="min-w-0">
        <Btn className="text-sm text-muted-foreground mb-2 gap-1">
          <ArrowLeft size={14} /> Back to COD reconciliation
        </Btn>
        <div className="flex flex-wrap items-center gap-2">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-5 w-28 rounded-full" />
        </div>
        <div className="mt-2 space-y-1">
          <Skeleton className="h-3 w-64 max-w-full" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Btn className="px-3 py-2 border border-input rounded-lg text-sm gap-1.5">
          <RefreshCw size={15} /> Refresh
        </Btn>
        <Btn className="px-3 py-2 border border-input rounded-lg text-sm gap-1.5">
          <Download size={15} /> Export CSV
        </Btn>
        <Btn className="px-3 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium gap-1.5">
          <Banknote size={15} /> Confirm bank receipt
        </Btn>
        <Btn className="px-3 py-2 border border-destructive/40 text-destructive rounded-lg text-sm gap-1.5">
          <XCircle size={15} /> Void
        </Btn>
      </div>
    </div>

    <div className="rounded-lg border border-border bg-muted/20 px-4 py-3 space-y-2">
      <div className="flex items-start gap-2">
        <ShieldAlert size={16} className="text-muted-foreground flex-shrink-0 mt-0.5" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </div>
    </div>

    <CodSummaryCardsSkeleton />

    <Card className="p-4 sm:p-5">
      <SectionTitle>Bank receipt</SectionTitle>
      <div className="mt-3 space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </Card>

    <Card className="overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <SectionTitle>Remittance lines</SectionTitle>
        <Skeleton className="h-3 w-3/4 mt-2" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1050px]">
          <HeadRow cols={['AWB / order', 'Order', 'COD', 'Deductions', 'Net', 'Allocate', 'Status', 'Decision']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 5 }).map((_, index) => (
              <tr key={index} className="align-top">
                <td className="px-3 py-3">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-3 w-20 mt-1.5" />
                </td>
                <td className="px-3 py-3">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-3 w-40 mt-1.5" />
                </td>
                <td className="px-3 py-3"><Skeleton className="h-4 w-14" /></td>
                <td className="px-3 py-3"><Skeleton className="h-4 w-12" /></td>
                <td className="px-3 py-3"><Skeleton className="h-4 w-14" /></td>
                <td className="px-3 py-3"><Skeleton className="h-4 w-16" /></td>
                <td className="px-3 py-3">
                  <Skeleton className="h-6 w-24 rounded-full" />
                  <Skeleton className="h-3 w-32 mt-1.5" />
                </td>
                <td className="px-3 py-3">
                  <div className="flex flex-col gap-1.5">
                    <Skeleton className="h-7 w-24 rounded-lg" />
                    <Skeleton className="h-7 w-16 rounded-lg" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  </div>
);

const COD_IMPORT_FIELD_LABELS = [
  'AWB', 'Order number', 'COD amount', 'Deductions', 'Net amount',
  'Remitted amount', 'CRF id', 'Remittance date', 'UTR',
];

export const CodImportSkeleton = () => (
  <div className="space-y-5">
    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
      <div className="min-w-0">
        <Btn className="text-sm text-muted-foreground mb-2 gap-1">
          <ArrowLeft size={14} /> Back to COD reconciliation
        </Btn>
        <h1 className="text-xl sm:text-2xl font-bold text-foreground">Import COD remittance CSV</h1>
        <div className="mt-2 space-y-1">
          <Skeleton className="h-3 w-full max-w-2xl" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </div>
      <div className="flex gap-2">
        <Btn className="px-3 py-2 border border-input rounded-lg text-sm gap-1.5">
          <Download size={15} /> Blank template
        </Btn>
        <Btn className="px-3 py-2 border border-input rounded-lg text-sm gap-1.5">
          <FlaskConical size={15} /> Synthetic fixture
        </Btn>
      </div>
    </div>

    <Card className="p-4 sm:p-5">
      <SectionTitle>1. Choose the CSV</SectionTitle>
      <Skeleton className="h-3 w-3/4 mt-2" />
      <div className="mt-3 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border px-4 py-8">
        <FileUp size={26} className="text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">Click to choose a CSV file</span>
        <span className="text-xs text-muted-foreground">CSV up to 5 MB · UTF-8, Windows-1252 or Latin-1</span>
      </div>
    </Card>

    <Card className="p-4 sm:p-5">
      <SectionTitle>2. Column mapping</SectionTitle>
      <Skeleton className="h-3 w-2/3 mt-2" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-4">
        {COD_IMPORT_FIELD_LABELS.map((label) => (
          <div key={label}>
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <Skeleton className="h-9 w-full rounded-lg mt-1" />
          </div>
        ))}
      </div>
    </Card>

    <CodSummaryCardsSkeleton count={4} cols="grid-cols-2 lg:grid-cols-4" className="" />

    <Card className="overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <SectionTitle>3. Preview matching</SectionTitle>
        <Skeleton className="h-3 w-3/4 mt-2" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px]">
          <HeadRow cols={['Row', 'AWB', 'Order', 'COD', 'Deductions', 'Net', 'Allocate', 'Status / note']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 4 }).map((_, index) => (
              <tr key={index}>
                <td className="px-3 py-2.5"><Skeleton className="h-3 w-6" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-4 w-20" /></td>
                <td className="px-3 py-2.5">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-3 w-16 mt-1.5" />
                </td>
                <td className="px-3 py-2.5"><Skeleton className="h-4 w-14" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-4 w-12" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-4 w-14" /></td>
                <td className="px-3 py-2.5"><Skeleton className="h-4 w-16" /></td>
                <td className="px-3 py-2.5">
                  <Skeleton className="h-6 w-24 rounded-full" />
                  <Skeleton className="h-3 w-40 mt-1.5" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>

    <Card className="p-4 sm:p-5">
      <SectionTitle>4. Batch details and import</SectionTitle>
      <Skeleton className="h-3 w-3/4 mt-2" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
        {['CRF / batch reference', 'Remittance date'].map((label) => (
          <div key={label}>
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <Skeleton className="h-9 w-full rounded-lg mt-1" />
          </div>
        ))}
        <div className="sm:col-span-2">
          <p className="text-xs font-medium text-muted-foreground">Notes (optional)</p>
          <Skeleton className="h-16 w-full rounded-lg mt-1" />
        </div>
      </div>
      <div className="mt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <Skeleton className="h-3 w-64 max-w-full" />
        <Btn className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium gap-2 justify-center">
          <FileUp size={15} /> Import batch
        </Btn>
      </div>
    </Card>
  </div>
);

export const CodManualBatchSkeleton = () => (
  <div className="space-y-5">
    <div>
      <Btn className="text-sm text-muted-foreground mb-2 gap-1">
        <ArrowLeft size={14} /> Back to COD reconciliation
      </Btn>
      <h1 className="text-xl sm:text-2xl font-bold text-foreground">New manual COD batch</h1>
      <div className="mt-2 space-y-1">
        <Skeleton className="h-3 w-full max-w-2xl" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </div>

    <Card className="p-4 sm:p-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {['CRF / batch reference', 'Remittance date'].map((label) => (
          <div key={label}>
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <Skeleton className="h-9 w-full rounded-lg mt-1" />
          </div>
        ))}
        <div className="sm:col-span-2">
          <p className="text-xs font-medium text-muted-foreground">Notes (optional)</p>
          <Skeleton className="h-16 w-full rounded-lg mt-1" />
        </div>
      </div>
    </Card>

    <Card className="overflow-hidden">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-2">
        <div>
          <SectionTitle>Remittance lines</SectionTitle>
          <Skeleton className="h-3 w-80 max-w-full mt-2" />
        </div>
        <Btn className="px-2.5 py-1.5 border border-input rounded-lg text-xs gap-1">
          <Plus size={13} /> Add line
        </Btn>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px]">
          <HeadRow cols={['AWB', 'Order number', 'COD amount', 'Deductions', 'Net amount', '']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 3 }).map((_, index) => (
              <tr key={index}>
                <td className="px-3 py-2"><Skeleton className="h-9 w-full rounded-lg" /></td>
                <td className="px-3 py-2"><Skeleton className="h-9 w-full rounded-lg" /></td>
                <td className="px-3 py-2"><Skeleton className="h-9 w-32 rounded-lg" /></td>
                <td className="px-3 py-2"><Skeleton className="h-9 w-28 rounded-lg" /></td>
                <td className="px-3 py-2"><Skeleton className="h-9 w-32 rounded-lg" /></td>
                <td className="px-3 py-2 text-right">
                  <Btn className="p-2 rounded-lg text-muted-foreground ml-auto"><Trash2 size={15} /></Btn>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>

    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <Skeleton className="h-3 w-72 max-w-full" />
      <Btn className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium gap-2 justify-center">
        <Save size={15} /> Create batch
      </Btn>
    </div>
  </div>
);

/* --------------------------- dispatch ------------------------------ */

// One entry per sidebar tab / sub-page, each rendering the skeleton that
// mirrors that page's real UI. Generic aliases are kept for compatibility.
