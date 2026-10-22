// src/pages/Cod/CodReconciliation.jsx
/**
 * Sales → COD Reconciliation.
 *
 * Two separate queues:
 *  - cash collection at delivery (creates the existing COD Payment), and
 *  - courier remittance batches (never create a Payment).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  Banknote,
  CheckCircle2,
  Download,
  Eye,
  FileUp,
  FlaskConical,
  Loader,
  PackageCheck,
  Plus,
  RefreshCw,
  ShieldAlert,
  Truck,
  Wallet,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  collectCodBulk,
  downloadCodFixture,
  downloadCodTemplate,
  getCodSummary,
  getCodAwaitingRemittance,
  getPendingCodOrders,
  listCodRemittances,
  saveBlob,
  simulateCodRemittance,
} from '../../api/cod';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import { formatDate, formatPrice } from '../../utils/format';
import { apiErrorMessage } from '../../utils/cod';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import {
  BatchStatusBadge,
  EmptyState,
  SourceBadge,
  SummaryCard,
} from '../../components/cod/CodShared';

const PAGE_SIZE = 15;
const STATUS_OPTIONS = [
  { value: '', label: 'All batches' },
  { value: 'pending', label: 'Awaiting bank credit' },
  { value: 'discrepancy', label: 'Discrepancy' },
  { value: 'reconciled', label: 'Reconciled' },
  { value: 'void', label: 'Void' },
];

const CodReconciliation = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const canView = canDo(user, 'cod.view', 'manager');
  const canReconcile = canDo(user, 'cod.reconcile', 'manager');
  const canCollect = canDo(user, 'orders.update', 'manager');

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [batches, setBatches] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [pending, setPending] = useState([]);
  const [awaitingRemittance, setAwaitingRemittance] = useState([]);
  const [awaitingRemittanceTotal, setAwaitingRemittanceTotal] = useState(0);
  const [awaitingRemittancePages, setAwaitingRemittancePages] = useState(1);
  const [awaitingRemittancePage, setAwaitingRemittancePage] = useState(1);
  const [tab, setTab] = useState('batches');
  const [status, setStatus] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [confirmState, setConfirmState] = useState(null);
  const loadSeq = useRef(0);

  // Only delivered + cod_pending orders need the manual fallback; everything
  // else is collected automatically by the DELIVERED webhook.
  const collectiblePending = pending.filter((order) => order.collectible);
  const collectionExceptions = summary?.awaiting_collection?.count || 0;
  const activeTab = tab === 'collection' && collectiblePending.length > 0
    ? 'collection'
    : tab === 'awaiting'
      ? 'awaiting'
      : 'batches';

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);


  const applyData = useCallback((data) => {
    setSummary(data.summary);
    setBatches(data.remittances);
    setTotal(data.total);
    setTotalPages(data.totalPages);
    setPending(data.pending);
    setAwaitingRemittance(data.awaitingRemittance);
    setAwaitingRemittanceTotal(data.awaitingRemittanceTotal);
    setAwaitingRemittancePages(data.awaitingRemittancePages);
  }, []);

  const fetchData = useCallback(async () => {
    const [summaryRes, batchRes, remittanceRes, pendingRes] = await Promise.all([
      getCodSummary(),
      listCodRemittances({
        page,
        limit: PAGE_SIZE,
        status: status || undefined,
        search: search || undefined,
      }),
      getCodAwaitingRemittance({ page: awaitingRemittancePage, limit: PAGE_SIZE }),
      canCollect ? getPendingCodOrders() : Promise.resolve({ data: { orders: [] } }),
    ]);
    return {
      summary: summaryRes.data || null,
      remittances: batchRes.data?.remittances || [],
      total: batchRes.data?.total || 0,
      totalPages: batchRes.data?.total_pages || 1,
      awaitingRemittance: remittanceRes.data?.orders || [],
      awaitingRemittanceTotal: remittanceRes.data?.total || 0,
      awaitingRemittancePages: remittanceRes.data?.total_pages || 1,
      pending: pendingRes.data?.orders || [],
    };
  }, [page, status, search, canCollect, awaitingRemittancePage]);

  const load = useCallback(async () => {
    const seq = loadSeq.current + 1;
    loadSeq.current = seq;
    try {
      const data = await fetchData();
      if (seq !== loadSeq.current) return false;
      applyData(data);
      return true;
    } catch (err) {
      if (seq === loadSeq.current) {
        toast.error(apiErrorMessage(err, 'Failed to load COD reconciliation'));
      }
      return false;
    } finally {
      if (seq === loadSeq.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [fetchData, applyData]);

  useEffect(() => {
    if (!canView) return undefined;
    let active = true;
    const seq = loadSeq.current + 1;
    loadSeq.current = seq;
    fetchData()
      .then((data) => {
        if (active && seq === loadSeq.current) applyData(data);
      })
      .catch((err) => {
        if (active && seq === loadSeq.current) {
          toast.error(apiErrorMessage(err, 'Failed to load COD reconciliation'));
        }
      })
      .finally(() => {
        if (active && seq === loadSeq.current) {
          setLoading(false);
          setRefreshing(false);
        }
      });
    return () => { active = false; };
  }, [canView, fetchData, applyData]);

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    const ok = await load();
    if (ok) toast.success('COD reconciliation refreshed');
  };

  const download = async (kind) => {
    try {
      const response = kind === 'template' ? await downloadCodTemplate() : await downloadCodFixture();
      saveBlob(
        response.data,
        kind === 'template' ? 'cod-remittance-template.csv' : 'SYNTHETIC_cod_remittance_fixture.csv',
      );
      if (kind === 'fixture') {
        toast.success('Downloaded synthetic fixture — it is not real Shiprocket data');
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Download failed'));
    }
  };

  const runSimulate = async () => {
    try {
      setBusy(true);
      const response = await simulateCodRemittance(5);
      toast.success('Synthetic batch created — clearly labelled, not Shiprocket data');
      setConfirmState(null);
      navigate(`/cod/${response.data.id}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not create a synthetic batch'));
    } finally {
      setBusy(false);
    }
  };

  const collect = async (orderIds) => {
    if (!orderIds.length) return;
    try {
      setBusy(true);
      const response = await collectCodBulk(orderIds);
      const collected = response.data?.collected || 0;
      const failed = response.data?.failed || 0;
      if (failed) {
        toast.error(`${collected} collected, ${failed} failed. Check order statuses.`);
      } else {
        toast.success(`${collected} COD order${collected === 1 ? '' : 's'} collected manually`);
      }
      setSelected([]);
      setConfirmState(null);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not collect COD cash'));
    } finally {
      setBusy(false);
    }
  };

  const toggleSelected = (id) => {
    setSelected((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
    );
  };

  if (!canView) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to view COD reconciliation.
      </div>
    );
  }

  if (loading && !summary) return <PageSkeleton type="cod" />;

  const selectedAmount = collectiblePending
    .filter((order) => selected.includes(order.id))
    .reduce((sum, order) => sum + Number(order.grand_total || 0), 0);

  return (
    <div>
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3 mb-6">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground">COD Reconciliation</h1>
          <p className="text-sm text-muted-foreground">
            Customer cash collection and courier remittance are tracked separately — remittance never creates a payment.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 w-full sm:flex sm:flex-wrap sm:items-center lg:w-auto">
          <button
            type="button"
            onClick={() => download('template')}
            className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-input rounded-lg text-xs sm:text-sm flex items-center gap-1.5 hover:bg-muted transition"
          >
            <Download size={15} /> Template
          </button>
          <button
            type="button"
            onClick={() => download('fixture')}
            className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-input rounded-lg text-xs sm:text-sm flex items-center gap-1.5 hover:bg-muted transition"
            title="Synthetic sample; not real Shiprocket data"
            aria-label="Download synthetic fixture"
          >
            <FlaskConical size={15} />
            <span className="sm:hidden">Fixture</span>
            <span className="hidden sm:inline">Synthetic fixture</span>
          </button>
          {canReconcile && (
            <>
              <button
                type="button"
                onClick={() => navigate('/cod/import')}
                className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 bg-primary text-primary-foreground rounded-lg text-xs sm:text-sm font-medium flex items-center gap-1.5 hover:bg-primary-hover transition"
              >
                <FileUp size={15} />
                <span className="sm:hidden">Import</span>
                <span className="hidden sm:inline">Import CSV</span>
              </button>
              <button
                type="button"
                onClick={() => navigate('/cod/new')}
                className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-input rounded-lg text-xs sm:text-sm flex items-center gap-1.5 hover:bg-muted transition"
              >
                <Plus size={15} />
                <span className="sm:hidden">Manual</span>
                <span className="hidden sm:inline">Manual batch</span>
              </button>
            </>
          )}
          {canReconcile && summary?.simulator_enabled && (
            <button
              type="button"
              onClick={() => setConfirmState({ kind: 'simulate' })}
              className="min-w-0 justify-center sm:justify-start px-2.5 sm:px-3 py-2 border border-warning/40 text-warning rounded-lg text-xs sm:text-sm flex items-center gap-1.5 hover:bg-warning/10 transition"
            >
              <FlaskConical size={15} />
              <span className="sm:hidden">Simulate</span>
              <span className="hidden sm:inline">Simulate (synthetic)</span>
            </button>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={refreshing}
            aria-busy={refreshing}
            aria-label="Refresh COD reconciliation"
            title="Refresh"
            className="justify-self-end sm:justify-self-auto flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-input text-muted-foreground hover:bg-muted hover:text-foreground transition disabled:opacity-50"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        {collectionExceptions > 0 && (
          <SummaryCard
            label="Collection exceptions"
            value={formatPrice(summary?.awaiting_collection?.amount || 0)}
            hint="auto-collection did not run"
            icon={Banknote}
            tone="text-warning"
          />
        )}
        <SummaryCard
          label="Awaiting remittance"
          value={formatPrice(summary?.awaiting_remittance?.amount || 0)}
          hint={`${summary?.awaiting_remittance?.count || 0} orders · See orders below`}
          icon={Truck}
          tone="text-info"
        />
        <SummaryCard
          label="Pending batches"
          value={summary?.pending_batches?.count || 0}
          hint={formatPrice(summary?.pending_batches?.amount || 0)}
          icon={Wallet}
        />
        <SummaryCard
          label="Open discrepancies"
          value={summary?.open_discrepancies || 0}
          hint={`${summary?.discrepancy_batches?.count || 0} batches flagged`}
          icon={ShieldAlert}
          tone="text-destructive"
        />
        <SummaryCard
          label="Reconciled this month"
          value={formatPrice(summary?.reconciled_this_month?.amount || 0)}
          hint={`${summary?.reconciled_this_month?.count || 0} bank receipts`}
          icon={CheckCircle2}
          tone="text-success"
        />
      </div>

      <div className="mb-4 rounded-lg border border-info/30 bg-info/5 px-4 py-3 text-xs text-muted-foreground flex items-start gap-2">
        <AlertCircle size={15} className="text-info flex-shrink-0 mt-0.5" />
        <p>
          Cash is <strong>collected automatically</strong> when Shiprocket marks a COD order delivered.
          The manual collection list below is only a fallback for legacy orders or missed webhooks.
          Collection creates the existing <strong>COD payment</strong> once; importing a Shiprocket
          remittance or confirming a bank credit only allocates that payout and never adds a second
          payment or extra revenue. Shiprocket does not publish a COD remittance API — batches come
          from the panel CSV or manual entry.
        </p>
      </div>

      <div className="flex gap-2 border-b border-border overflow-x-auto mb-6">
        <button
          type="button"
          onClick={() => setTab('batches')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition ${
            activeTab === 'batches'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Remittance batches ({total})
        </button>
        <button
          type="button"
          onClick={() => setTab('awaiting')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition ${
            activeTab === 'awaiting'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Awaiting remittance ({summary?.awaiting_remittance?.count || 0})
        </button>
        {collectiblePending.length > 0 && (
          <button
            type="button"
            onClick={() => setTab('collection')}
            className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition ${
              activeTab === 'collection'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            Collection exceptions ({collectiblePending.length})
          </button>
        )}
      </div>

      {activeTab === 'batches' && (
        <>
          <div className="flex flex-col sm:flex-row gap-2 mb-4">
            <input
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search CRF or UTR…"
              className="w-full sm:max-w-sm px-3 py-2 border border-input rounded-lg text-sm bg-card"
              aria-label="Search remittance batches"
            />
            <select
              value={status}
              onChange={(event) => { setStatus(event.target.value); setPage(1); }}
              className="w-full sm:w-auto px-3 py-2 border border-input rounded-lg text-sm bg-card"
              aria-label="Filter remittance batches by status"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value || 'all'} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>

          <div className="bg-card rounded-xl shadow-sm border border-border overflow-hidden">
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full min-w-[900px]">
                <thead className="bg-muted">
                  <tr>
                    {['CRF / batch', 'Date', 'Status', 'Gross COD', 'Deductions', 'Net expected', 'Bank credit', 'Lines', ''].map((label) => (
                      <th key={label || 'actions'} className={`px-4 py-3 text-xs font-medium text-muted-foreground uppercase tracking-wider ${label ? 'text-left' : 'text-right'}`}>
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {batches.map((batch) => (
                    <tr key={batch.id} className="hover:bg-muted/40">
                      <td className="px-4 py-3">
                        <div className="font-medium text-foreground">{batch.crf_id}</div>
                        <SourceBadge source={batch.source} synthetic={batch.synthetic} />
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">{formatDate(batch.remittance_date)}</td>
                      <td className="px-4 py-3"><BatchStatusBadge status={batch.status} /></td>
                      <td className="px-4 py-3 text-sm">{formatPrice(batch.gross_cod)}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{formatPrice(batch.deductions_total)}</td>
                      <td className="px-4 py-3 text-sm font-medium">{formatPrice(batch.net_expected)}</td>
                      <td className="px-4 py-3 text-sm">
                        {batch.bank_credit_amount == null ? '—' : formatPrice(batch.bank_credit_amount)}
                        {batch.utr && <div className="text-xs text-muted-foreground">UTR {batch.utr}</div>}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {batch.item_count}
                        {batch.flagged_count > 0 && (
                          <span className="ml-1 text-xs text-destructive">({batch.flagged_count} flagged)</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => navigate(`/cod/${batch.id}`)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 border border-input rounded-lg text-xs hover:bg-muted transition"
                        >
                          <Eye size={13} /> View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="md:hidden divide-y divide-border">
              {batches.map((batch) => (
                <div key={batch.id} className="p-4 space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-foreground break-all">{batch.crf_id}</p>
                      <SourceBadge source={batch.source} synthetic={batch.synthetic} />
                    </div>
                    <BatchStatusBadge status={batch.status} />
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                    <div>
                      <p className="text-muted-foreground">Date</p>
                      <p className="text-foreground">{formatDate(batch.remittance_date)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Lines</p>
                      <p className="text-foreground">
                        {batch.item_count}
                        {batch.flagged_count > 0 && (
                          <span className="ml-1 text-destructive">({batch.flagged_count} flagged)</span>
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Gross COD</p>
                      <p className="text-foreground">{formatPrice(batch.gross_cod)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Deductions</p>
                      <p className="text-foreground">{formatPrice(batch.deductions_total)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Net expected</p>
                      <p className="font-medium text-foreground">{formatPrice(batch.net_expected)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Bank credit</p>
                      <p className="text-foreground">
                        {batch.bank_credit_amount == null ? '—' : formatPrice(batch.bank_credit_amount)}
                      </p>
                      {batch.utr && <p className="text-[11px] text-muted-foreground break-all">UTR {batch.utr}</p>}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate(`/cod/${batch.id}`)}
                    className="w-full inline-flex items-center justify-center gap-1 px-3 py-2 border border-input rounded-lg text-xs hover:bg-muted transition"
                  >
                    <Eye size={13} /> View batch
                  </button>
                </div>
              ))}
            </div>

            {batches.length === 0 && (
              <EmptyState
                title="No remittance batches yet"
                hint="Import the Shiprocket COD remittance CSV, enter a batch manually, or create a synthetic development batch."
              />
            )}
            {total > 0 && (
              <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">
                  Page {page} of {totalPages} · {total} batch{total === 1 ? '' : 'es'}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage((value) => Math.max(1, value - 1))}
                    className="flex-1 sm:flex-none px-3 py-1.5 border border-input rounded-lg text-sm disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={page >= totalPages}
                    onClick={() => setPage((value) => value + 1)}
                    className="flex-1 sm:flex-none px-3 py-1.5 border border-input rounded-lg text-sm disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {activeTab === 'awaiting' && (
        <div className="bg-card rounded-xl shadow-sm border border-border overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="font-semibold text-foreground">Delivered COD orders awaiting courier payout</h2>
            <p className="text-xs text-muted-foreground mt-1">
              {awaitingRemittanceTotal} orders · {formatPrice(summary?.awaiting_remittance?.amount || 0)} outstanding.
              {' '}These orders already have their customer COD payment recorded; remittance only allocates the courier payout.
            </p>
          </div>
          {awaitingRemittance.length > 0 ? (
            <>
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead className="bg-muted">
                    <tr>
                      {['Order', 'Customer', 'AWB / courier', 'Delivered', 'Order total', 'Remitted', 'Outstanding'].map((label) => (
                        <th key={label} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {awaitingRemittance.map((order) => (
                      <tr key={order.id} className="hover:bg-muted/40">
                        <td className="px-4 py-3">
                          <button type="button" onClick={() => navigate(`/orders/${order.id}`)} className="text-sm font-medium text-primary hover:underline">
                            {order.order_number}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {order.customer?.full_name || '—'}
                          {order.customer?.email && <div className="text-xs">{order.customer.email}</div>}
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {order.awb_code || '—'}
                          {order.courier_name && <div className="text-xs">{order.courier_name}</div>}
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">{formatDate(order.delivered_at)}</td>
                        <td className="px-4 py-3 text-sm">{formatPrice(order.grand_total)}</td>
                        <td className="px-4 py-3 text-sm">{formatPrice(order.remitted_amount)}</td>
                        <td className="px-4 py-3 text-sm font-semibold">{formatPrice(order.remaining_amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="md:hidden divide-y divide-border">
                {awaitingRemittance.map((order) => (
                  <div key={order.id} className="p-4 space-y-3">
                    <div>
                      <button type="button" onClick={() => navigate(`/orders/${order.id}`)} className="text-sm font-semibold text-primary hover:underline break-all">
                        {order.order_number}
                      </button>
                      <p className="text-xs text-muted-foreground mt-1">
                        {order.customer?.full_name || '—'}{order.customer?.email ? ` · ${order.customer.email}` : ''}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div><p className="text-muted-foreground">AWB / courier</p><p>{order.awb_code || '—'}{order.courier_name ? ` · ${order.courier_name}` : ''}</p></div>
                      <div><p className="text-muted-foreground">Delivered</p><p>{formatDate(order.delivered_at)}</p></div>
                      <div><p className="text-muted-foreground">Order total</p><p>{formatPrice(order.grand_total)}</p></div>
                      <div><p className="text-muted-foreground">Remitted</p><p>{formatPrice(order.remitted_amount)}</p></div>
                    </div>
                    <p className="text-sm font-semibold">Outstanding payout: {formatPrice(order.remaining_amount)}</p>
                  </div>
                ))}
              </div>
              {awaitingRemittanceTotal > PAGE_SIZE && (
                <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <p className="text-sm text-muted-foreground">Page {awaitingRemittancePage} of {awaitingRemittancePages} · {awaitingRemittanceTotal} orders</p>
                  <div className="flex gap-2">
                    <button type="button" disabled={awaitingRemittancePage <= 1} onClick={() => setAwaitingRemittancePage((value) => Math.max(1, value - 1))} className="flex-1 sm:flex-none px-3 py-1.5 border border-input rounded-lg text-sm disabled:opacity-40">Previous</button>
                    <button type="button" disabled={awaitingRemittancePage >= awaitingRemittancePages} onClick={() => setAwaitingRemittancePage((value) => value + 1)} className="flex-1 sm:flex-none px-3 py-1.5 border border-input rounded-lg text-sm disabled:opacity-40">Next</button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <EmptyState title="No orders awaiting remittance" hint="Delivered COD orders with an outstanding courier payout will appear here." />
          )}
        </div>
      )}

      {activeTab === 'collection' && (
        <div className="bg-card rounded-xl shadow-sm border border-border overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex flex-col sm:flex-row justify-between gap-2">
            <div>
              <h2 className="font-semibold text-foreground">COD delivered but not auto-collected</h2>
              <p className="text-xs text-muted-foreground">
                Collection happens automatically when Shiprocket marks an order delivered. This list is
                only for legacy orders or missed webhooks — collecting here creates the one and only COD
                payment for each order. {selected.length} selected.
              </p>
            </div>
            {canCollect && (
              <button
                type="button"
                disabled={!selected.length || busy}
                onClick={() => setConfirmState({ kind: 'collect', ids: selected })}
                className="w-full sm:w-auto px-3 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50 inline-flex items-center justify-center gap-1.5"
              >
                {busy ? <Loader size={15} className="animate-spin" /> : <PackageCheck size={15} />}
                Collect manually ({formatPrice(selectedAmount)})
              </button>
            )}
          </div>
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead className="bg-muted">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    <input
                      type="checkbox"
                      aria-label="Select all collectible COD orders"
                      checked={collectiblePending.length > 0 && collectiblePending.every((order) => selected.includes(order.id))}
                      onChange={(event) => setSelected(event.target.checked ? collectiblePending.map((order) => order.id) : [])}
                      className="rounded border-input"
                    />
                  </th>
                  {['Order', 'Customer', 'Amount', 'Status', 'Placed', 'Cash'].map((label) => (
                    <th key={label} className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {collectiblePending.map((order) => (
                  <tr key={order.id} className="hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={`Select ${order.order_number}`}
                        disabled={!order.collectible || !canCollect}
                        checked={selected.includes(order.id)}
                        onChange={() => toggleSelected(order.id)}
                        className="rounded border-input"
                      />
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-foreground">{order.order_number}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {order.customer?.full_name || '—'}
                      {order.customer?.email && <div className="text-xs">{order.customer.email}</div>}
                    </td>
                    <td className="px-4 py-3 text-sm font-medium">{formatPrice(order.grand_total)}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{order.status}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{formatDate(order.placed_at)}</td>
                    <td className="px-4 py-3">
                      {order.collectible && canCollect ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => setConfirmState({ kind: 'collect', ids: [order.id] })}
                          className="px-2.5 py-1.5 bg-success text-white rounded-lg text-xs font-medium hover:bg-success/90 disabled:opacity-50 transition-colors"
                        >
                          Collect manually
                        </button>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {order.collectible ? 'No collection permission' : 'Not delivered'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {collectiblePending.length > 0 && (
            <div className="md:hidden">
              <div className="px-4 py-2.5 border-b border-border flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <label className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label="Select all collectible COD orders"
                    checked={collectiblePending.length > 0 && collectiblePending.every((order) => selected.includes(order.id))}
                    onChange={(event) => setSelected(event.target.checked ? collectiblePending.map((order) => order.id) : [])}
                    className="rounded border-input"
                  />
                  Select all collectible
                </label>
                <span>{selected.length} selected</span>
              </div>
              <div className="divide-y divide-border">
                {collectiblePending.map((order) => (
                  <div key={order.id} className="p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground break-all">{order.order_number}</p>
                        <p className="text-xs text-muted-foreground break-all">
                          {order.customer?.full_name || '—'}
                          {order.customer?.email && <span className="block">{order.customer.email}</span>}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        aria-label={`Select ${order.order_number}`}
                        disabled={!order.collectible || !canCollect}
                        checked={selected.includes(order.id)}
                        onChange={() => toggleSelected(order.id)}
                        className="mt-0.5 rounded border-input shrink-0"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                      <div>
                        <p className="text-muted-foreground">Amount</p>
                        <p className="font-medium text-foreground">{formatPrice(order.grand_total)}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Status</p>
                        <p className="text-foreground">{order.status}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Placed</p>
                        <p className="text-foreground">{formatDate(order.placed_at)}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Cash</p>
                        <p className="text-foreground">
                          {order.collectible ? 'Awaiting manual collection' : 'Not delivered'}
                        </p>
                      </div>
                    </div>
                    {order.collectible && canCollect ? (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setConfirmState({ kind: 'collect', ids: [order.id] })}
                        className="w-full px-3 py-2 bg-success text-white rounded-lg text-xs font-medium hover:bg-success/90 disabled:opacity-50 transition-colors"
                      >
                        Collect manually
                      </button>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        {order.collectible ? 'No collection permission' : 'Not delivered'}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      )}

      <ConfirmDialog
        open={!!confirmState}
        title={
          confirmState?.kind === 'simulate'
            ? 'Create a synthetic remittance batch?'
            : 'Record a manual COD collection?'
        }
        message={
          confirmState?.kind === 'simulate'
            ? 'This creates a clearly-labelled SYNTHETIC batch using your delivered COD test orders. It is a development aid, not a real Shiprocket remittance, and never calls Shiprocket.'
            : `Normally collection is automatic on delivery. This fallback records the existing COD payment for ${confirmState?.ids?.length || 0} order(s) and does not create a remittance.`
        }
        confirmLabel={confirmState?.kind === 'simulate' ? 'Create synthetic batch' : 'Collect manually'}
        tone="primary"
        busy={busy}
        onConfirm={() => {
          if (confirmState?.kind === 'simulate') runSimulate();
          else collect(confirmState?.ids || []);
        }}
        onClose={() => { if (!busy) setConfirmState(null); }}
      />
    </div>
  );
};

export default CodReconciliation;
