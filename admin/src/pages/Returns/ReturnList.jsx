import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, PackageOpen, RefreshCw, Search } from 'lucide-react';
import { returnAPI } from '../../api/returns';
import { useAuth } from '../../context/AuthContext';
import { formatDate, formatPrice } from '../../utils/format';
import { createReturnLoader, hasReturnPermission, returnError, RETURN_REASONS, RETURN_STATUS_LABELS } from '../../utils/returns';
import PageSkeleton from '../../components/ui/PageSkeleton';

const inputClass = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground';
const buttonClass = 'inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50';

export default function ReturnList() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const orderId = params.get('order_id') || undefined;
  const [filters, setFilters] = useState({ search: '', status_filter: '', reason: '', page: 1 });
  const [search, setSearch] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const allowed = hasReturnPermission(user, 'orders.view');
  const loader = useMemo(() => createReturnLoader({
    load: returnAPI.list,
    onStart: () => { setLoading(true); setError(null); setListing(null); },
    onResult: (data) => { setListing(data); setLoading(false); },
    onError: (failure) => { setError(returnError(failure)); setLoading(false); },
  }), []);
  useEffect(() => {
    if (allowed) loader.run({ ...filters, search: filters.search || undefined, status_filter: filters.status_filter || undefined,
      reason: filters.reason || undefined, order_id: orderId, limit: 15 });
    return () => loader.cancel();
  }, [allowed, filters, loader, refresh, orderId]);
  if (!allowed) return <p role="alert" className="p-5 text-destructive">You do not have permission to view product returns.</p>;
  if (loading && !listing && !error) return <PageSkeleton type="returns" />;
  const rows = listing?.returns || [];
  return <div className="space-y-6">
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"><div><h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-3"><PackageOpen size={26} /> Product returns</h1><p className="text-sm text-muted-foreground mt-1">Review delivered-item returns, receipt, inspection and refunds.</p></div><button type="button" className={buttonClass} disabled={loading} onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button></div>
    <form className="rounded-xl border border-border bg-card p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" onSubmit={(event) => { event.preventDefault(); setFilters((previous) => ({ ...previous, search: search.trim(), page: 1 })); }}>
      <label className="text-xs text-muted-foreground">Order or customer<div className="flex gap-2 mt-1"><input className={inputClass} value={search} maxLength={200} placeholder="Order number, name or email" onChange={(event) => setSearch(event.target.value)} /><button type="submit" className={buttonClass} aria-label="Search returns"><Search size={17} /></button></div></label>
      <label className="text-xs text-muted-foreground">Status<select className={`${inputClass} mt-1`} value={filters.status_filter} onChange={(event) => setFilters((previous) => ({ ...previous, status_filter: event.target.value, page: 1 }))}><option value="">All statuses</option>{Object.entries(RETURN_STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="text-xs text-muted-foreground">Reason<select className={`${inputClass} mt-1`} value={filters.reason} onChange={(event) => setFilters((previous) => ({ ...previous, reason: event.target.value, page: 1 }))}><option value="">All reasons</option>{Object.entries(RETURN_REASONS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="flex items-end"><button type="button" className={buttonClass} onClick={() => { setSearch(''); setFilters({ search: '', status_filter: '', reason: '', page: 1 }); }}>Clear filters</button>{orderId && <Link to="/returns" className={`${buttonClass} ml-2`}>All orders</Link>}</div>
    </form>
    {error ? <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-5"><p>{error}</p><button type="button" className={`${buttonClass} mt-3`} onClick={() => setRefresh((value) => value + 1)}>Retry</button></div>
      : loading ? <div role="status" className="space-y-3">{[1, 2, 3].map((key) => <div key={key} className="h-24 bg-muted animate-pulse rounded-xl" />)}</div>
      : !rows.length ? <div className="rounded-xl border border-border bg-card p-12 text-center"><PackageOpen className="mx-auto text-muted-foreground mb-3" size={36} /><h2 className="font-semibold">No returns found</h2><p className="text-sm text-muted-foreground mt-2">New customer requests appear here. Try adjusting your filters.</p></div>
      : <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="hidden md:block overflow-x-auto"><table className="w-full text-sm text-left"><thead className="bg-muted/60 text-xs text-muted-foreground"><tr>{['Return / order', 'Customer', 'Items / reason', 'Refund', 'Status', 'Requested', ''].map((label, index) => <th key={index} className="p-4 font-semibold">{label}</th>)}</tr></thead><tbody className="divide-y divide-border">{rows.map((row) => <tr key={row.id} className="hover:bg-muted/30"><td className="p-4"><Link to={`/returns/${row.id}`} className="font-semibold text-primary hover:underline">{row.return_number}</Link><p className="text-xs text-muted-foreground mt-1">{row.order_number}</p></td><td className="p-4"><p>{row.customer?.name}</p><p className="text-xs text-muted-foreground">{row.customer?.email}</p></td><td className="p-4"><p>{row.items.reduce((sum, item) => sum + item.quantity, 0)} unit(s)</p><p className="text-xs text-muted-foreground mt-1">{row.reason_label}</p></td><td className="p-4 font-medium whitespace-nowrap">{formatPrice(row.refund_amount)}</td><td className="p-4"><span className="inline-block rounded-full bg-muted px-3 py-1 text-xs font-medium">{RETURN_STATUS_LABELS[row.status]}</span></td><td className="p-4 text-xs text-muted-foreground whitespace-nowrap">{formatDate(row.created_at)}</td><td className="p-4"><Link to={`/returns/${row.id}`} className={buttonClass}>Review</Link></td></tr>)}</tbody></table></div>
        <div className="md:hidden divide-y divide-border">{rows.map((row) => <Link key={row.id} to={`/returns/${row.id}`} className="block p-4 space-y-2 hover:bg-muted/30"><div className="flex justify-between gap-3"><strong className="text-primary">{row.return_number}</strong><span className="text-xs rounded-full px-2 py-1 bg-muted">{RETURN_STATUS_LABELS[row.status]}</span></div><p className="text-sm">{row.order_number} · {row.customer?.name}</p><p className="text-xs text-muted-foreground wrap-break-word">{row.customer?.email}</p><div className="flex justify-between gap-2 text-sm"><span>{row.reason_label}</span><strong>{formatPrice(row.refund_amount)}</strong></div><p className="text-xs text-muted-foreground">{formatDate(row.created_at)}</p></Link>)}</div>
      </div>}
    {listing && <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground"><span>{listing.total} return(s) · Page {filters.page} of {listing.total_pages}</span><div className="flex gap-2"><button className={buttonClass} aria-label="Previous page" disabled={loading || filters.page <= 1} onClick={() => setFilters((previous) => ({ ...previous, page: previous.page - 1 }))}><ChevronLeft size={17} /></button><button className={buttonClass} aria-label="Next page" disabled={loading || filters.page >= listing.total_pages} onClick={() => setFilters((previous) => ({ ...previous, page: previous.page + 1 }))}><ChevronRight size={17} /></button></div></div>}
  </div>;
}
