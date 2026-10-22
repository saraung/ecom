// src/pages/StoreSettings/StoreSettings.jsx
/**
 * Store policy settings (requires settings.manage — admins only).
 *
 * The money rules that used to require a deploy to change: tax, shipping,
 * COD limits, restocking fees, refund window, unpaid-order expiry.
 * Scale contract (must match the backend math): tax_rate is edited as a
 * percentage but STORED as a fraction (18 ↔ 0.18, pricing multiplies
 * directly). Restocking fees are edited AND stored as percentages
 * (5 ↔ 5.0, the refund engine divides by 100 itself). Only fields with
 * `fraction: true` are converted on load/save — never add it to a
 * percent-stored field or fees silently shift 100×.
 * Every save is audited server-side with a before/after diff.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { SlidersHorizontal, RefreshCw, Save, Database, HardDrive, History, Undo2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { getStoreSettings, getStoreSettingsHistory, restoreStoreSettings, updateStoreSettings } from '../../api/settings';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { currencySymbol, taxLabel } from '../../utils/format';
import { formatDate } from '../../utils/format';

const pct = (fraction) => ((Number(fraction) || 0) * 100).toFixed(2).replace(/\.?0+$/, '');

const SECTIONS = [
  {
    title: 'Tax & pricing',
    fields: [
      { key: 'tax_rate', label: '{tax} / tax rate (%)', hint: 'Applied on the post-discount subtotal', fraction: true, min: 0, max: 100 },
    ],
  },
  {
    title: 'Shipping',
    fields: [
      { key: 'free_shipping_threshold', label: 'Free shipping above ({cur})', hint: 'Orders at or above this ship free', min: 0 },
      { key: 'shipping_cost', label: 'Flat shipping cost ({cur})', hint: 'Charged below the threshold', min: 0 },
    ],
  },
  {
    title: 'Cash on Delivery',
    fields: [
      { key: 'cod_fee', label: 'COD fee ({cur})', hint: 'Added to COD orders, payable on delivery', min: 0 },
      { key: 'cod_min_order_value', label: 'COD minimum order ({cur})', hint: 'COD refused below this total', min: 0 },
      { key: 'cod_max_order_value', label: 'COD maximum order ({cur})', hint: 'COD refused above this total', min: 0 },
    ],
  },
  {
    title: 'Cancellations & refunds',
    fields: [
      { key: 'restocking_fee_pending', label: 'Restocking fee — pending orders (%)', min: 0, max: 100 },
      { key: 'restocking_fee_confirmed', label: 'Restocking fee — confirmed orders (%)', min: 0, max: 100 },
      { key: 'restocking_fee_processing', label: 'Restocking fee — processing orders (%)', min: 0, max: 100 },
      { key: 'refund_processing_days', label: 'Refund reflection window (days)', hint: 'Shown to customers in refund messages', min: 1, max: 30, integer: true },
    ],
  },
  {
    title: 'Unpaid orders',
    fields: [
      { key: 'pending_order_expiry_minutes', label: 'Auto-cancel unpaid orders after (minutes)', hint: 'Stock released, payment intent voided', min: 5, max: 1440, integer: true },
    ],
  },
];

// SECTIONS labels carry {cur}/{tax} tokens resolved against the live
// region at render/validate time (module scope would freeze INR defaults).
const labelFor = (f) =>
  f.label.replace('{cur}', currencySymbol()).replace('{tax}', taxLabel());

const toForm = (data) => {
  const form = {};
  SECTIONS.forEach((s) => s.fields.forEach((f) => {
    const raw = Number(data?.[f.key]);
    form[f.key] = Number.isFinite(raw) ? String(f.fraction ? pct(raw) : raw) : '';
  }));
  return form;
};

const StoreSettings = () => {
  const { user } = useAuth();
  const allowed = canDo(user, 'settings.manage', 'admin');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({});
  const [saved, setSaved] = useState({});
  const [source, setSource] = useState('environment');
  const [history, setHistory] = useState([]);
  const [restoringId, setRestoringId] = useState(null);
  const [confirmState, setConfirmState] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getStoreSettings();
      const data = res.data || {};
      const next = toForm(data);
      setForm(next);
      setSaved(next);
      setSource(data.source || 'environment');
      try {
        const hist = await getStoreSettingsHistory(5);
        setHistory(hist.data?.entries || []);
      } catch {
        // History is a nice-to-have (e.g. older server without the
        // endpoint): the form must still work without it.
        setHistory([]);
      }
    } catch {
      toast.error('Failed to load store settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to manage store settings.
      </div>
    );
  }

  if (loading) return <PageSkeleton type="store-settings" />;

  const dirty = JSON.stringify(form) !== JSON.stringify(saved);

  const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleRestore = (entry) => {
    const keys = entry.changes.map((c) => c.key).join(', ');
    setConfirmState({
      kind: 'restore',
      title: 'Restore settings',
      message: `Undo this change (${keys})? Those values revert to what they were before, everything else stays as-is. The restore is audited too, so it can be undone as well.`,
      entry,
    });
  };

  const runConfirmed = async () => {
    if (!confirmState) return;
    if (confirmState.kind === 'restore') {
      const entry = confirmState.entry;
      try {
        setRestoringId(entry.audit_id);
        await restoreStoreSettings(entry.audit_id);
        toast.success('Settings restored to the earlier values');
        load();
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Failed to restore settings');
      } finally {
        setRestoringId(null);
        setConfirmState(null);
      }
      return;
    }
    const payload = confirmState.payload;
    if (!payload) {
      setConfirmState(null);
      return;
    }
    try {
      setSaving(true);
      await updateStoreSettings(payload);
      toast.success('Store settings saved — live immediately');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save store settings');
    } finally {
      setSaving(false);
      setConfirmState(null);
    }
  };

  const handleSave = () => {
    // Validate + convert: tax_rate back to a fraction, blanks = untouched.
    // Restocking fees are stored as percentages — saved raw.
    const payload = {};
    for (const section of SECTIONS) {
      for (const f of section.fields) {
        const raw = (form[f.key] ?? '').trim();
        if (raw === '' || raw === saved[f.key]) continue;
        const num = Number(raw);
        if (!Number.isFinite(num)) {
          toast.error(`${labelFor(f)}: enter a number`);
          return;
        }
        if (f.integer && !Number.isInteger(num)) {
          toast.error(`${labelFor(f)}: whole numbers only`);
          return;
        }
        if (num < f.min || (f.max != null && num > f.max)) {
          toast.error(`${labelFor(f)}: must be between ${f.min} and ${f.max}`);
          return;
        }
        payload[f.key] = f.fraction ? num / 100 : num;
      }
    }
    if (Object.keys(payload).length === 0) {
      toast.error('No changes to save');
      return;
    }
    if (payload.cod_min_order_value != null || payload.cod_max_order_value != null) {
      const lo = payload.cod_min_order_value ?? Number(saved.cod_min_order_value);
      const hi = payload.cod_max_order_value ?? Number(saved.cod_max_order_value);
      if (hi < lo) {
        toast.error('COD maximum must be >= COD minimum');
        return;
      }
    }
    setConfirmState({
      kind: 'save',
      title: 'Save store settings',
      message: 'Save these money rules? Checkout pricing, COD eligibility and refund messages change immediately for every customer.',
      payload,
    });
  };

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2 break-words">
            <SlidersHorizontal size={20} className="text-primary shrink-0" />
            Store Settings
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
            {source === 'database' ? <Database size={12} /> : <HardDrive size={12} />}
            {source === 'database'
              ? 'Customized — values below override the server defaults'
              : 'Showing server defaults — saving creates the customized set'}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="px-2.5 py-1.5 border border-input rounded-lg text-xs flex items-center gap-1 hover:bg-muted transition"
        >
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-4">
        {SECTIONS.map((section) => (
          <div key={section.title} className="bg-card rounded-xl border border-border p-4">
            <h2 className="text-[15px] font-semibold text-foreground mb-3">{section.title}</h2>
            <div className="space-y-3">
              {section.fields.map((f) => {
                const label = labelFor(f);
                return (
                <div key={f.key} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-3">
                  <label
                    htmlFor={`store-${f.key}`}
                    className="text-sm text-foreground leading-snug min-w-0"
                    title={f.hint}
                  >
                    {label}
                  </label>
                  <input
                    id={`store-${f.key}`}
                    type="number"
                    min={f.min}
                    max={f.max}
                    step={f.integer ? 1 : 'any'}
                    value={form[f.key] ?? ''}
                    onChange={(e) => set(f.key, e.target.value)}
                    className="w-full sm:w-32 shrink-0 px-2.5 py-2.5 sm:py-2 border border-input rounded-lg text-base sm:text-sm bg-background text-foreground sm:text-right focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {history.length > 0 && (
        <div className="bg-card rounded-xl border border-border p-4 mt-3 sm:mt-4">
          <h2 className="text-[15px] font-semibold text-foreground flex items-center gap-2 mb-1">
            <History size={16} className="text-muted-foreground shrink-0" />
            Change history
          </h2>
          <p className="text-xs text-muted-foreground mb-3">
            Restoring undoes that save only — other values stay as-is, and the restore itself is audited.
          </p>
          <div className="space-y-2">
            {history.map((entry) => (
              <div
                key={entry.audit_id}
                className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 p-3 rounded-lg border border-border bg-muted/40"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-muted-foreground break-all">
                    {entry.created_at
                      ? formatDate(entry.created_at, {
                          day: '2-digit', month: 'short', year: 'numeric',
                          hour: '2-digit', minute: '2-digit',
                        })
                      : '—'}
                    {entry.actor_email ? ` · ${entry.actor_email}` : ''}
                    {entry.action === 'settings.store_restored' ? ' · restore' : ''}
                  </p>
                  <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
                    {entry.changes.map((c) => (
                      <span key={c.key} className="text-xs font-mono text-foreground break-all">
                        {c.key}: {String(c.before)} → {String(c.after)}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleRestore(entry)}
                  disabled={restoringId !== null || saving}
                  className="w-full sm:w-auto shrink-0 px-3 py-2.5 sm:py-1.5 border border-input rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 hover:bg-muted transition disabled:opacity-50"
                >
                  {restoringId === entry.audit_id ? (
                    <RefreshCw size={13} className="animate-spin" />
                  ) : (
                    <Undo2 size={13} />
                  )}
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 flex justify-stretch sm:justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !dirty}
          className="w-full sm:w-auto justify-center px-5 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium flex items-center gap-2 hover:bg-primary-hover transition disabled:opacity-50"
        >
          {saving ? (
            <>
              <RefreshCw size={16} className="animate-spin" />
              Saving…
            </>
          ) : (
            <>
              <Save size={16} />
              Save Store Settings
            </>
          )}
        </button>
      </div>
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Save store settings'}
        message={confirmState?.message}
        confirmLabel={confirmState?.kind === 'restore' ? 'Restore' : 'Save'}
        cancelLabel="Cancel"
        tone="primary"
        busy={saving || restoringId !== null}
        onConfirm={runConfirmed}
        onClose={() => { if (!saving && restoringId === null) setConfirmState(null); }}
      />
    </div>
  );
};

export default StoreSettings;
