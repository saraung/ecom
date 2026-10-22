// src/pages/Audit/AuditLog.jsx
/**
 * Read-only admin audit log viewer (requires reports.view).
 *
 * Least privilege, mirrored from the backend router:
 * - ``reports.view`` alone      → operational entities only
 *   (order, refund, coupon, product, category, notification, settings).
 * - ``+ users.view``            → identity entities too (user, role, invite);
 *   requesting those filters without the permission is a 403, not an
 *   empty list, so the UI hides what it cannot read.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, RefreshCw, ShieldAlert } from 'lucide-react';
import toast from 'react-hot-toast';
import { getAuditLog } from '../../api/audit';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import PageSkeleton from '../../components/ui/PageSkeleton';
import { formatDate } from '../../utils/format';

const ITEMS_PER_PAGE = 20;

const OPERATIONAL_ENTITIES = [
  'order', 'refund', 'coupon', 'product', 'category', 'notification', 'settings',
  'review', 'content',
];
const IDENTITY_ENTITIES = ['user', 'role', 'invite'];

/** before/after rendered as a compact JSON block when a row is expanded. */
const formatPayload = (payload) => (
  payload && Object.keys(payload).length
    ? JSON.stringify(payload, null, 2)
    : '—'
);

const AuditLog = () => {
  const { user } = useAuth();
  const allowed = canDo(user, 'reports.view', 'manager');
  // Identity entries (user/role/invite) also require users.view.
  const seesIdentity = canDo(user, 'users.view', 'admin');

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  const [entity, setEntity] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [expandedId, setExpandedId] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getAuditLog({
        page,
        limit: ITEMS_PER_PAGE,
        entity: entity || undefined,
      });
      setRows(res.data?.entries || []);
      setTotal(res.data?.total || 0);
      setTotalPages(res.data?.total_pages || 1);
    } catch (err) {
      setRows([]);
      setTotal(0);
      setTotalPages(1);
      toast.error(err.response?.data?.detail || 'Failed to load the audit log');
    } finally {
      setLoading(false);
    }
  }, [page, entity]);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to view the audit log.
      </div>
    );
  }

  if (loading) return <PageSkeleton type="audit-log" />;


  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Audit Log</h1>
          <p className="text-sm text-muted-foreground">
            {total} {total === 1 ? 'entry' : 'entries'} — newest first
            {!seesIdentity && ' (operational actions only)'}
          </p>
        </div>
        <div className="flex gap-2">
          <label htmlFor="audit-entity" className="sr-only">
            Filter audit entries by entity
          </label>
          <select
            id="audit-entity"
            value={entity}
            onChange={(e) => { setEntity(e.target.value); setPage(1); }}
            className="border border-input rounded-lg px-3 py-2 text-sm bg-card text-foreground"
          >
            <option value="">All entities</option>
            {OPERATIONAL_ENTITIES.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
            {/* Identity filters would 403 without users.view — hide them. */}
            {seesIdentity && IDENTITY_ENTITIES.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={load}
            className="px-3 py-2 border border-input rounded-lg text-sm flex items-center gap-1 hover:bg-muted transition"
          >
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </div>

      {!seesIdentity && (
        <div className="mb-4 flex items-start gap-2 text-xs text-muted-foreground bg-muted rounded-lg p-3">
          <ShieldAlert size={14} className="mt-0.5 shrink-0" />
          You&apos;re seeing operational actions only. Identity actions
          (user / role / invite changes) require the users.view permission.
        </div>
      )}

      <div className="bg-card rounded-xl border border-border overflow-hidden">
        {/* Desktop: table */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full min-w-[820px]">
            <thead className="bg-muted border-b border-border">
              <tr>
                {['', 'Time', 'Actor', 'Action', 'Entity', 'IP'].map((head) => (
                  <th
                    key={head || 'expand'}
                    className="text-left px-4 py-3 text-xs uppercase text-muted-foreground"
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    No audit entries recorded yet.
                  </td>
                </tr>
              )}
              {rows.map((entry) => {
                const expanded = expandedId === entry.id;
                return (
                  <React.Fragment key={entry.id}>
                    <tr className="hover:bg-muted/50">
                      <td className="pl-3 pr-0 py-3 w-8">
                        <button
                          type="button"
                          onClick={() => setExpandedId(expanded ? null : entry.id)}
                          aria-expanded={expanded}
                          aria-label={expanded ? 'Hide entry details' : 'Show entry details'}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-xs whitespace-nowrap text-muted-foreground">
                        {formatDate(entry.created_at)}
                      </td>
                      <td className="px-4 py-3 text-xs truncate max-w-[200px] text-foreground">
                        {entry.actor_email || 'system'}
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-foreground">
                        {entry.action}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {entry.entity}
                        {entry.entity_id ? `:${String(entry.entity_id).slice(0, 8)}` : ''}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {entry.ip_address || '—'}
                      </td>
                    </tr>

                    {expanded && (
                      <tr className="bg-muted/30">
                        <td />
                        <td colSpan={5} className="px-4 pb-4">
                          <div className="grid gap-3 sm:grid-cols-2">
                            <div>
                              <p className="text-xs uppercase text-muted-foreground mb-1">
                                Before
                              </p>
                              <pre className="text-xs bg-background border border-border rounded-lg p-2 overflow-x-auto">
                                {formatPayload(entry.before)}
                              </pre>
                            </div>
                            <div>
                              <p className="text-xs uppercase text-muted-foreground mb-1">
                                After
                              </p>
                              <pre className="text-xs bg-background border border-border rounded-lg p-2 overflow-x-auto">
                                {formatPayload(entry.after)}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Mobile: vertical timeline with icon rail (Figma audit-log pattern) */}
        <div className="md:hidden">
          {rows.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              No audit entries recorded yet.
            </p>
          )}
          <ol className="divide-y divide-border">
            {rows.map((entry) => {
              const expanded = expandedId === entry.id;
              return (
                <li key={entry.id} className="flex gap-3 p-4">
                  <button
                    type="button"
                    onClick={() => setExpandedId(expanded ? null : entry.id)}
                    aria-expanded={expanded}
                    aria-label={expanded ? 'Hide entry details' : 'Show entry details'}
                    className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground"
                  >
                    {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  </button>
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="font-mono text-xs font-medium text-foreground break-all">
                      {entry.action}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {entry.entity}
                      {entry.entity_id ? `:${String(entry.entity_id).slice(0, 8)}` : ''}
                      {' · '}
                      {formatDate(entry.created_at, {
                        day: 'numeric',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {entry.actor_email || 'system'}
                      {entry.ip_address ? ` · ${entry.ip_address}` : ''}
                    </p>
                    {expanded && (
                      <div className="grid gap-2 pt-1">
                        <div>
                          <p className="text-xs uppercase text-muted-foreground mb-1">Before</p>
                          <pre className="text-xs bg-background border border-border rounded-lg p-2 overflow-x-auto">
                            {formatPayload(entry.before)}
                          </pre>
                        </div>
                        <div>
                          <p className="text-xs uppercase text-muted-foreground mb-1">After</p>
                          <pre className="text-xs bg-background border border-border rounded-lg p-2 overflow-x-auto">
                            {formatPayload(entry.after)}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>

        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Showing {((page - 1) * ITEMS_PER_PAGE) + 1} -{' '}
              {Math.min(page * ITEMS_PER_PAGE, total)} of {total} entries
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AuditLog;

