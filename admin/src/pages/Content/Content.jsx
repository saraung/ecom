// src/pages/Content/Content.jsx
/**
 * Storefront content blocks (requires content.manage).
 *
 * List page: keyed slots (`announcement.bar` store-wide strip,
 * `home.hero` homepage block). Create/edit live on dedicated pages
 * (/content/new, /content/:id/edit) like Product/Category/Coupon forms.
 * Publish windows make campaigns self-expiring; is_active is the kill
 * switch. Every write is audited server-side (entity "content").
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Images,
  Plus,
  Pencil,
  Trash2,
  RefreshCw,
  Eye,
  EyeOff,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getContentBlocks,
  updateContentBlock,
  deleteContentBlock,
} from '../../api/content';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatDate } from '../../utils/format';

const KNOWN_KEYS = [
  { key: 'announcement.bar', desc: 'Thin strip above the storefront header' },
  { key: 'home.hero', desc: 'Homepage headline + subcopy + CTA' },
];


const liveState = (block) => {
  if (!block.is_active) return { label: 'Off', className: 'bg-muted text-muted-foreground' };
  const now = new Date();
  if (block.starts_at && new Date(block.starts_at) > now)
    return { label: 'Scheduled', className: 'bg-warning/20 text-warning' };
  if (block.ends_at && new Date(block.ends_at) <= now)
    return { label: 'Expired', className: 'bg-destructive/15 text-destructive' };
  return { label: 'Live', className: 'bg-success/15 text-success' };
};

const Content = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const allowed = canDo(user, 'content.manage', 'manager');

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [confirmState, setConfirmState] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getContentBlocks();
      setRows(res.data?.items || []);
    } catch {
      toast.error('Failed to load content blocks');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  const handleToggle = async (block) => {
    try {
      setBusyId(block.id);
      await updateContentBlock(block.id, { is_active: !block.is_active });
      toast.success(block.is_active ? 'Block taken offline' : 'Block is live');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not update block');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = (block) => {
    setConfirmState({
      title: 'Delete content block',
      message: `Delete the "${block.key}" block? Its slot falls back to the hardcoded storefront content.`,
      block,
    });
  };

  const runConfirmed = async () => {
    const block = confirmState?.block;
    if (!block) {
      setConfirmState(null);
      return;
    }
    try {
      setBusyId(block.id);
      await deleteContentBlock(block.id);
      toast.success('Content block deleted');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not delete block');
    } finally {
      setBusyId(null);
      setConfirmState(null);
    }
  };

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to manage content.
      </div>
    );
  }

  if (loading) return <PageSkeleton type="banners" />;

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2 break-words">
            <Images size={22} className="text-primary shrink-0" />
            Banners
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Announcement bar, homepage hero and promo banners — no deploy needed
          </p>
        </div>
        <div className="flex flex-col sm:flex-row w-full sm:w-auto gap-2">
          <button
            type="button"
            onClick={load}
            className="px-3 py-2.5 sm:py-2 border border-input rounded-lg text-sm flex items-center justify-center gap-1 hover:bg-muted transition"
          >
            <RefreshCw size={15} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => navigate('/content/new')}
            className="px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg text-sm flex items-center justify-center gap-1 hover:bg-primary-hover transition"
          >
            <Plus size={15} />
            New block
          </button>
        </div>
      </div>

      {/* Known slots hint */}
      <div className="bg-card border border-border rounded-xl p-4 mb-6">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
          Live slots
        </p>
        <div className="flex flex-wrap gap-2">
          {KNOWN_KEYS.map(({ key, desc }) => {
            const liveCount = rows.filter((r) => r.key === key && liveState(r).label === 'Live').length;
            return (
              <span
                key={key}
                title={desc}
                className={`text-xs px-2.5 py-1 rounded-full font-mono ${
                  liveCount > 0 ? 'bg-success/15 text-success' : 'bg-muted text-muted-foreground'
                }`}
              >
                {key}{liveCount > 0 ? ` (${liveCount})` : ' (empty)'}
              </span>
            );
          })}
        </div>
      </div>

      <div className="bg-card rounded-xl border border-border overflow-hidden">
        {/* Desktop: table */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full min-w-[760px]">
            <thead className="bg-muted border-b border-border">
              <tr>
                {['Slot', 'Title', 'Window', 'State', 'Actions'].map((head, i) => (
                  <th
                    key={head}
                    className={`text-left px-4 py-3 text-xs uppercase text-muted-foreground${i === 4 ? ' text-right' : ''}`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    No content blocks yet — create the announcement bar above.
                  </td>
                </tr>
              )}
              {rows.map((block) => {
                const state = liveState(block);
                return (
                  <tr key={block.id} className="hover:bg-muted/50">
                    <td className="px-4 py-3 text-xs font-mono text-foreground">
                      {block.key}
                      <span className="text-muted-foreground"> #{block.sort_order ?? 0}</span>
                    </td>
                    <td className="px-4 py-3 max-w-[260px]">
                      <p className="text-sm font-medium text-foreground truncate">{block.title}</p>
                      {block.body && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">{block.body}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                      {formatDate(block.starts_at)} → {formatDate(block.ends_at)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs ${state.className}`}>
                        {state.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 justify-end">
                        <button
                          type="button"
                          disabled={busyId === block.id}
                          onClick={() => handleToggle(block)}
                          title={block.is_active ? 'Take offline' : 'Put live'}
                          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors disabled:opacity-50"
                        >
                          {block.is_active ? <EyeOff size={15} /> : <Eye size={15} />}
                        </button>
                        <button
                          type="button"
                          onClick={() => navigate(`/content/${block.id}/edit`)}
                          title="Edit"
                          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          type="button"
                          disabled={busyId === block.id}
                          onClick={() => handleDelete(block)}
                          title="Delete"
                          className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors disabled:opacity-50"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Mobile: stacked cards */}
        <div className="md:hidden divide-y divide-border">
          {rows.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              No content blocks yet — create the announcement bar above.
            </p>
          )}
          {rows.map((block) => {
            const state = liveState(block);
            return (
              <div key={block.id} className="p-4 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-mono text-foreground truncate min-w-0">{block.key}</p>
                  <span className={`px-2 py-1 rounded-full text-xs shrink-0 ${state.className}`}>
                    {state.label}
                  </span>
                </div>
                <p className="text-sm font-medium text-foreground">{block.title}</p>
                {block.body && (
                  <p className="text-sm text-muted-foreground">{block.body}</p>
                )}
                <p className="text-xs text-muted-foreground">
                  {formatDate(block.starts_at)} → {formatDate(block.ends_at)}
                </p>
                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    disabled={busyId === block.id}
                    onClick={() => handleToggle(block)}
                    className="flex-1 px-2 py-2.5 border border-input rounded-lg text-sm flex items-center justify-center gap-1 hover:bg-muted disabled:opacity-50"
                  >
                    {block.is_active ? <EyeOff size={14} /> : <Eye size={14} />}
                    {block.is_active ? 'Take offline' : 'Put live'}
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(`/content/${block.id}/edit`)}
                    className="flex-1 px-2 py-2.5 border border-input rounded-lg text-sm flex items-center justify-center gap-1 hover:bg-muted"
                  >
                    <Pencil size={14} />
                    Edit
                  </button>
                  <button
                    type="button"
                    disabled={busyId === block.id}
                    onClick={() => handleDelete(block)}
                    className="px-3 py-2.5 text-destructive border border-input rounded-lg text-sm flex items-center justify-center hover:bg-destructive/10 disabled:opacity-50"
                    aria-label="Delete block"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Delete content block'}
        message={confirmState?.message}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        tone="danger"
        busy={busyId !== null}
        onConfirm={runConfirmed}
        onClose={() => { if (busyId === null) setConfirmState(null); }}
      />
    </div>
  );
};

export default Content;
