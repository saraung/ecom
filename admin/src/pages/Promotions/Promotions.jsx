// src/pages/Promotions/Promotions.jsx
import React, { useEffect, useState } from 'react';
import { Megaphone, Send, Users, RefreshCw, Inbox, Trash2, Mail } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  sendPromotionalNotification,
  getSentPromotions,
  deletePromotionalNotification,
  getPromotionAudienceEstimate,
} from '../../api/notifications';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import { formatDate } from '../../utils/format';
import ConfirmDialog from '../../components/ui/ConfirmDialog';

const MAX_TITLE = 120;
const MAX_MESSAGE = 500;


const parseItems = (data) => {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return data.items || data.results || data.data || [];
};

const Promotions = () => {
  const { user } = useAuth();
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [link, setLink] = useState('');
  const [sending, setSending] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [retractingId, setRetractingId] = useState(null);
  // Email fan-out is opt-in per send and ALWAYS resets to off afterwards —
  // a remembered "on" would become a de-facto default and cause an
  // accidental mass email. Emails can't be retracted, feed rows can.
  const [sendEmail, setSendEmail] = useState(false);
  const [estimate, setEstimate] = useState(null);
  const [confirmState, setConfirmState] = useState(null);

  // Permission gate, matching the backend's require_perm("promotions.send").
  // Deliberately NOT a role-string check: `users.role` only stores the
  // primary role, so a stacked role set could otherwise lock this page out.
  const allowed = canDo(user, 'promotions.send');

  const fetchHistory = async () => {
    try {
      setHistoryLoading(true);
      const response = await getSentPromotions({ skip: 0, limit: 20 });
      setHistory(parseItems(response?.data));
    } catch {
      // Backend may not expose history yet — show empty state quietly.
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const fetchEstimate = async () => {
    try {
      const response = await getPromotionAudienceEstimate();
      setEstimate(response?.data ?? null);
    } catch {
      // Older backend without the estimate endpoint — hide counts quietly.
      setEstimate(null);
    }
  };

  useEffect(() => {
    if (allowed) {
      fetchHistory();
      fetchEstimate();
    }
  }, [allowed]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!title.trim() || !message.trim()) {
      toast.error('Title and message are required');
      return;
    }

    setConfirmState({
      kind: 'send',
      titleText: title.trim(),
      messageText: message.trim(),
      linkText: link.trim(),
      sendEmailAtConfirm: sendEmail,
      title: 'Send Promotion',
      message: sendEmail
        ? 'Send this promotional message to all SHOPPER accounts (in-app feed) AND email every shopper whose Email Notifications toggle is on? Staff/admins are excluded automatically. Emails cannot be unsent — only feed rows can be retracted.'
        : 'Send this promotional message to all SHOPPER accounts? Staff/admins are excluded automatically. This cannot be undone.',
      confirmLabel: 'Send',
      tone: 'danger',
    });
  };

  const runConfirmed = async () => {
    if (!confirmState) return;
    if (confirmState.kind === 'send') {
      const { titleText, messageText, linkText, sendEmailAtConfirm } = confirmState;
      try {
        setSending(true);
        const payload = { title: titleText, message: messageText };
        if (linkText) payload.link = linkText;
        if (sendEmailAtConfirm) payload.send_email = true;

        const response = await sendPromotionalNotification(payload);
        const recipients =
          response?.data?.recipients_count ??
          response?.data?.total_recipients ??
          response?.data?.delivered ??
          response?.data?.count;
        const emailsQueued = response?.data?.emails_queued ?? 0;

        toast.success(
          typeof recipients === 'number'
            ? `Promotion sent to ${recipients} users!` +
              (emailsQueued > 0 ? ` ${emailsQueued} emails queued.` : '')
            : 'Promotion sent to all users!'
        );
        setTitle('');
        setMessage('');
        setLink('');
        setSendEmail(false);
        fetchHistory();
        fetchEstimate();
      } catch (error) {
        toast.error(error.response?.data?.detail || 'Failed to send promotion');
      } finally {
        setSending(false);
        setConfirmState(null);
      }
      return;
    }

    const { broadcastId } = confirmState;
    try {
      setRetractingId(broadcastId);
      const response = await deletePromotionalNotification(broadcastId);
      const deleted =
        response?.data?.deleted_count ?? response?.data?.count ?? 0;
      toast.success(
        typeof deleted === 'number'
          ? `Retracted promotion — removed from ${deleted} user notifications`
          : 'Promotion retracted'
      );
      fetchHistory();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to retract promotion');
    } finally {
      setRetractingId(null);
      setConfirmState(null);
    }
  };

  const handleRetract = async (promotion) => {
    const broadcastId =
      promotion.broadcast_id ?? promotion.id ?? promotion.promotional_id;

    if (broadcastId == null) {
      toast.error('This promotion cannot be retracted (no broadcast id)');
      return;
    }

    setConfirmState({
      kind: 'retract',
      broadcastId,
      title: 'Retract Promotion',
      message:
        'Retract this promotion? It will be removed from every user\u2019s ' +
        'notifications and from this history. This cannot be undone.',
      confirmLabel: 'Retract',
      tone: 'danger',
    });
  };

  if (!allowed) {
    return (
      <div className="text-center py-16">
        <Megaphone size={32} className="mx-auto text-muted-foreground mb-3" />
        <h1 className="text-xl font-bold text-foreground">Access denied</h1>
        <p className="text-sm text-muted-foreground mt-1">
          You need manager permissions to send promotions.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2 break-words">
          <Megaphone size={24} className="text-primary shrink-0" />
          Promotions
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Broadcast promotional messages to shoppers — staff/manager/admin
          accounts never receive promos (zero-permission targeting).
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        {/* Compose form */}
        <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6 min-w-0">
          <h2 className="text-lg font-semibold text-foreground mb-4">New Promotion</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Title <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value.slice(0, MAX_TITLE))}
                placeholder="e.g. Diwali Sale is live! 🎉"
                className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
              <p className="text-xs text-muted-foreground mt-1 text-right">
                {title.length}/{MAX_TITLE}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Message <span className="text-destructive">*</span>
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value.slice(0, MAX_MESSAGE))}
                placeholder="e.g. Flat 25% off on all sneakers this week only. Use code DIWALI25 at checkout!"
                rows={5}
                className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
              />
              <p className="text-xs text-muted-foreground mt-1 text-right">
                {message.length}/{MAX_MESSAGE}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Deep link <span className="text-muted-foreground font-normal">(optional)</span>
              </label>
              <input
                type="text"
                value={link}
                onChange={(e) => setLink(e.target.value)}
                placeholder="e.g. /products?sale=diwali"
                className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Screen in the user app that opens when the notification is tapped.
              </p>
            </div>

            {/* Live preview of what the user will see */}
            <div className="border border-border rounded-lg p-4 bg-muted/50">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                Preview (user notification)
              </p>
              <div className="flex items-start gap-3">
                <span className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 bg-warning/20 text-warning">
                  <Megaphone size={17} />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {title.trim() || 'Your promotion title'}
                  </p>
                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {message.trim() || 'Your promotion message will appear here.'}
                  </p>
                </div>
              </div>
            </div>

            {/* Email fan-out: opt-in per send, defaults off every time */}
            <label className="flex items-start gap-3 p-4 rounded-lg border border-border bg-muted/50 cursor-pointer">
              <input
                type="checkbox"
                checked={sendEmail}
                onChange={(e) => setSendEmail(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-primary"
              />
              <span>
                <span className="text-sm font-medium text-foreground flex items-center gap-1.5">
                  <Mail size={14} />
                  Also send by email
                  {estimate != null && (
                    <span className="font-normal text-muted-foreground">
                      (~{estimate.email_recipients} shoppers with Email Notifications on)
                    </span>
                  )}
                </span>
                <span className="block text-xs text-muted-foreground mt-1">
                  Shoppers who turned Email Notifications off are skipped automatically.
                  Staff never receive promos. Emails cannot be retracted.
                </span>
              </span>
            </label>

            <div className="flex items-center justify-between pt-2">
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Users size={14} />
                {estimate
                  ? `Recipients: ~${estimate.feed_recipients} in-app · ~${estimate.email_recipients} by email`
                  : 'Recipients: shoppers only (active + push-enabled + zero permissions)'}
              </span>
              <button
                type="submit"
                disabled={sending || !title.trim() || !message.trim()}
                className="btn-primary flex items-center gap-2 disabled:opacity-50"
              >
                {sending ? (
                  <>
                    <RefreshCw size={18} className="animate-spin" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Send size={18} />
                    Send to All Users
                  </>
                )}
              </button>
            </div>
          </form>
        </div>

        {/* Sent history */}
        <div className="bg-card rounded-xl shadow-sm border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">Sent Promotions</h2>
            <button
              onClick={() => {
                fetchHistory();
                fetchEstimate();
              }}
              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
              title="Refresh history"
            >
              <RefreshCw size={16} className={historyLoading ? 'animate-spin' : ''} />
            </button>
          </div>

          {historyLoading && history.length === 0 ? (
            <div className="space-y-3 py-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="animate-pulse bg-foreground/10 rounded-lg h-14" />
              ))}
            </div>
          ) : history.length === 0 ? (
            <div className="py-10 text-center">
              <Inbox size={28} className="mx-auto text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">No promotions sent yet</p>
              <p className="text-xs text-muted-foreground mt-1">
                Your broadcast history will appear here
              </p>
            </div>
          ) : (
            <div className="space-y-3 overflow-y-auto max-h-[40rem]">
              {history.map((promotion) => (
                <div
                  key={promotion.id}
                  className="border border-border rounded-lg p-4 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground flex items-center gap-2">
                        <Megaphone size={14} className="text-warning flex-shrink-0" />
                        <span className="truncate">{promotion.title}</span>
                      </p>
                      {promotion.message && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {promotion.message}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {(promotion.recipients_count ??
                        promotion.total_recipients ??
                        promotion.delivered) != null && (
                        <span className="text-xs bg-success/15 text-success px-2 py-1 rounded-full font-medium flex items-center gap-1">
                          <Users size={12} />
                          {promotion.recipients_count ??
                            promotion.total_recipients ??
                            promotion.delivered}
                        </span>
                      )}
                      {(promotion.email_requested || (promotion.emails_sent ?? 0) > 0) && (
                        <span
                          className="text-xs bg-primary-soft text-primary-soft-foreground px-2 py-1 rounded-full font-medium flex items-center gap-1"
                          title={
                            (promotion.emails_failed ?? 0) > 0
                              ? `${promotion.emails_failed} emails failed`
                              : 'All emails delivered'
                          }
                        >
                          <Mail size={12} />
                          {promotion.emails_sent ?? 0} emailed
                        </span>
                      )}
                      <button
                        onClick={() => handleRetract(promotion)}
                        disabled={retractingId != null}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Retract this promotion from all users"
                      >
                        <Trash2
                          size={15}
                          className={
                            retractingId === (promotion.broadcast_id ?? promotion.id ?? promotion.promotional_id)
                              ? 'animate-spin'
                              : ''
                          }
                        />
                      </button>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    {formatDate(promotion.created_at ?? promotion.sent_at)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Confirm'}
        message={confirmState?.message}
        confirmLabel={confirmState?.confirmLabel || 'Confirm'}
        cancelLabel="Cancel"
        tone={confirmState?.tone || 'danger'}
        busy={sending || retractingId != null}
        onClose={() => { if (!sending && retractingId == null) setConfirmState(null); }}
        onConfirm={runConfirmed}
      />
    </div>
  );
};

export default Promotions;

