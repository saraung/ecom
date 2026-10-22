// src/pages/Invites/Invites.jsx
/**
 * Staff invites (requires users.manage_roles).
 *
 * Slack-style onboarding: the invited person never gets a password up front —
 * the emailed single-use link is the proof of inbox control, and they choose
 * their own credentials on /accept-invite.
 *
 * Guardrail: the backend refuses an invite into any role granting a
 * permission the inviter does not hold themselves (grant ⊆ held), and
 * re-checks the inviter's authority when the link is used — so a manager
 * can never mint an admin peer, even with a stale link.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Link2, Loader, Lock, Mail, Plus, RefreshCw, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { createInvite, getInvites, resendInvite, revokeInvite } from '../../api/invites';
import { getRoles } from '../../api/roles';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatDate } from '../../utils/format';

const STATUS_BADGE = {
  pending: 'bg-warning/20 text-warning',
  accepted: 'bg-success/15 text-success',
  expired: 'bg-muted text-muted-foreground',
  revoked: 'bg-destructive/15 text-destructive',
};

const statusBadgeClass = (status) => STATUS_BADGE[status] || 'bg-muted text-foreground';

const Invites = () => {
  const { user } = useAuth();
  const allowed = canDo(user, 'users.manage_roles', 'admin');

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  const [roles, setRoles] = useState([]);
  const [rolesFailed, setRolesFailed] = useState(false);
  const [email, setEmail] = useState('');
  const [picked, setPicked] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [sending, setSending] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [confirmState, setConfirmState] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getInvites(statusFilter || undefined);
      setRows(res.data || []);
    } catch {
      toast.error('Failed to load invites');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const loadRoles = useCallback(async () => {
    try {
      const res = await getRoles();
      setRoles(res.data || []);
      setRolesFailed(false);
    } catch {
      setRolesFailed(true);
    }
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
  }, [allowed, load]);

  useEffect(() => {
    if (!allowed) return;
    // The role picker needs the live catalog (custom roles included).
    loadRoles();
  }, [allowed, loadRoles]);

  // Permissions the inviter holds (when the session carries them): roles
  // granting anything outside this set are refused server-side. Marked
  // inline so the refusal is never a surprise. Legacy sessions without a
  // permission list mark nothing — the server still blocks.
  const myPerms = Array.isArray(user?.permissions) && user.permissions.length > 0
    ? new Set(user.permissions)
    : null;
  const missingFor = (role) => {
    if (!myPerms) return [];
    return (role.permissions || []).filter((k) => !myPerms.has(k));
  };

  const toggleRole = (slug) => {
    setPicked((prev) => (
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]
    ));
  };

  const handleInvite = async (e) => {
    e.preventDefault();
    if (!email.trim() || picked.length === 0) {
      toast.error('An email address and at least one role are required');
      return;
    }
    try {
      setSending(true);
      await createInvite({ email: email.trim(), role_slugs: picked });
      toast.success(`Invite sent to ${email.trim()}`);
      setEmail('');
      setPicked([]);
      load();
    } catch (err) {
      // 403 = escalation block, 400 = duplicate/unknown role.
      toast.error(err.response?.data?.detail || 'Could not send the invite');
    } finally {
      setSending(false);
    }
  };

  const handleResend = async (invite) => {
    try {
      setBusyId(invite.id);
      await resendInvite(invite.id);
      toast.success(`New link emailed to ${invite.email}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not resend the invite');
    } finally {
      setBusyId(null);
    }
  };

  const handleRevoke = (invite) => {
    setConfirmState({
      title: 'Revoke invite',
      message: `Revoke the invite for ${invite.email}?`,
      invite,
    });
  };

  const runConfirmed = async () => {
    const invite = confirmState?.invite;
    if (!invite) {
      setConfirmState(null);
      return;
    }
    try {
      setBusyId(invite.id);
      await revokeInvite(invite.id);
      toast.success('Invite revoked');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not revoke the invite');
    } finally {
      setBusyId(null);
      setConfirmState(null);
    }
  };

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to manage staff invites.
      </div>
    );
  }

  if (loading) return <PageSkeleton type="invites" />;


  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Staff Invites</h1>
          <p className="text-sm text-muted-foreground">
            Invite by email — the link expires in 7 days and works once.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="px-3 py-2 border border-input rounded-lg text-sm flex items-center gap-1 hover:bg-muted transition"
        >
          <RefreshCw size={15} />
          Refresh
        </button>
      </div>

      <form
        onSubmit={handleInvite}
        className="bg-card border border-border rounded-xl p-4 mb-6"
      >
        <div className="flex flex-col md:flex-row gap-3">
          <div className="flex-1">
            <label htmlFor="invite-email" className="sr-only">Email address</label>
            <input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teammate@store.com"
              className="w-full border border-input rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              required
            />
          </div>
          <button
            type="submit"
            disabled={sending}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm flex items-center gap-1 justify-center disabled:opacity-60"
          >
            {sending
              ? <Loader className="animate-spin" size={15} />
              : <Plus size={15} />}
            {sending ? 'Sending…' : 'Send invite'}
          </button>
        </div>

        <fieldset className="mt-3">
          <legend className="text-xs uppercase text-muted-foreground mb-2">
            Roles
          </legend>
          <div className="flex flex-wrap gap-2 items-center">
            {roles.map((role) => {
              const missing = missingFor(role);
              return (
                <label
                  key={role.id}
                  title={
                    missing.length > 0
                      ? `Grants ${missing.join(', ')} which you don't hold — the server will refuse this invite`
                      : (role.description || role.slug)
                  }
                  className={`text-xs flex gap-1.5 items-center border rounded-full px-2.5 py-1 cursor-pointer transition ${
                    picked.includes(role.slug)
                      ? 'border-primary bg-primary/10 text-foreground'
                      : 'border-border text-muted-foreground hover:bg-muted'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={picked.includes(role.slug)}
                    onChange={() => toggleRole(role.slug)}
                  />
                  {missing.length > 0 && (
                    <Lock size={11} className="text-warning shrink-0" />
                  )}
                  {role.name || role.slug}
                </label>
              );
            })}
            {roles.length === 0 && !rolesFailed && (
              <span className="text-xs text-muted-foreground">
                Loading roles…
              </span>
            )}
            {roles.length === 0 && rolesFailed && (
              <span className="text-xs text-muted-foreground flex items-center gap-2">
                Couldn&apos;t load roles.
                <button
                  type="button"
                  onClick={loadRoles}
                  className="px-2.5 py-1 border border-input rounded-lg font-medium hover:bg-muted transition-colors"
                >
                  Retry
                </button>
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-2 flex items-start gap-1.5">
            <Link2 size={13} className="mt-0.5 shrink-0" />
            A role marked with a lock grants permissions you don&apos;t hold
            yourself — the server refuses such invites, so ask an admin to
            send those.
          </p>
        </fieldset>
      </form>



      <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-4">
        <label htmlFor="invite-status" className="sr-only">
          Filter invites by status
        </label>
        <select
          id="invite-status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-input rounded-lg px-3 py-2.5 sm:py-2 text-sm bg-card text-foreground w-full sm:w-auto"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="accepted">Accepted</option>
          <option value="expired">Expired</option>
          <option value="revoked">Revoked</option>
        </select>
        {statusFilter && (
          <p className="text-xs text-muted-foreground">
            Showing {rows.length} {statusFilter} invite{rows.length === 1 ? '' : 's'}
          </p>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {/* Desktop: table */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full min-w-[680px]">
            <thead className="bg-muted border-b border-border">
              <tr>
                {['Email', 'Roles', 'Status', 'Expires', 'Actions'].map((head, i) => (
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
                    {statusFilter
                      ? `No ${statusFilter} invites.`
                      : 'No invites yet — send the first one above.'}
                  </td>
                </tr>
              )}
              {rows.map((invite) => (
                <tr key={invite.id} className="hover:bg-muted/50">
                  <td className="px-4 py-3 text-sm text-foreground">{invite.email}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {(invite.role_slugs || []).join(', ') || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs ${statusBadgeClass(invite.status)}`}>
                      {invite.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {formatDate(invite.expires_at)}
                  </td>
                  <td className="px-4 py-3">
                    {invite.status === 'pending' ? (
                      <div className="flex gap-2 justify-end">
                        <button
                          type="button"
                          disabled={busyId === invite.id}
                          onClick={() => handleResend(invite)}
                          className="text-xs px-2 py-1 border border-input rounded flex items-center gap-1 hover:bg-muted disabled:opacity-60"
                        >
                          {busyId === invite.id
                            ? <Loader className="animate-spin" size={12} />
                            : <Mail size={12} />}
                          Resend
                        </button>
                        <button
                          type="button"
                          disabled={busyId === invite.id}
                          onClick={() => handleRevoke(invite)}
                          className="text-xs px-2 py-1 text-destructive border border-input rounded flex items-center gap-1 hover:bg-destructive/10 disabled:opacity-60"
                        >
                          <Trash2 size={12} />
                          Revoke
                        </button>
                      </div>
                    ) : (
                      <p className="text-right text-xs text-muted-foreground">
                        {invite.status === 'accepted'
                          ? 'Account created'
                          : 'No action needed'}
                      </p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Mobile: stacked cards */}
        <div className="md:hidden divide-y divide-border">
          {rows.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              {statusFilter
                ? `No ${statusFilter} invites.`
                : 'No invites yet — send the first one above.'}
            </p>
          )}
          {rows.map((invite) => (
            <div key={invite.id} className="p-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-foreground truncate min-w-0">
                  {invite.email}
                </p>
                <span className={`px-2 py-1 rounded-full text-xs shrink-0 ${statusBadgeClass(invite.status)}`}>
                  {invite.status}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="truncate">
                  {(invite.role_slugs || []).join(', ') || '—'}
                </span>
                <span className="shrink-0">
                  Expires {formatDate(invite.expires_at)}
                </span>
              </div>
              {invite.status === 'pending' ? (
                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    disabled={busyId === invite.id}
                    onClick={() => handleResend(invite)}
                    className="flex-1 text-sm px-2 py-2.5 border border-input rounded-lg flex items-center justify-center gap-1 hover:bg-muted disabled:opacity-60"
                  >
                    {busyId === invite.id
                      ? <Loader className="animate-spin" size={13} />
                      : <Mail size={13} />}
                    Resend
                  </button>
                  <button
                    type="button"
                    disabled={busyId === invite.id}
                    onClick={() => handleRevoke(invite)}
                    className="flex-1 text-sm px-2 py-2.5 text-destructive border border-input rounded-lg flex items-center justify-center gap-1 hover:bg-destructive/10 disabled:opacity-60"
                  >
                    <Trash2 size={13} />
                    Revoke
                  </button>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {invite.status === 'accepted' ? 'Account created' : 'No action needed'}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Revoke invite'}
        message={confirmState?.message}
        confirmLabel="Revoke"
        cancelLabel="Cancel"
        tone="danger"
        busy={busyId !== null}
        onConfirm={runConfirmed}
        onClose={() => { if (busyId === null) setConfirmState(null); }}
      />
    </div>
  );
};

export default Invites;
