// src/components/ui/ConfirmDialog.jsx
// Reusable confirmation dialog — styled replacement for native window.confirm.
//
// Design: mirrors AdminCancelDialog / RefundDialog + shadcn Alert Dialog:
//   fixed inset-0 z-50 bg-black/50 → bg-card rounded-xl border border-border
//   max-w-md p-6, icon + title + text-sm text-muted-foreground description,
//   footer Cancel (btn-outline) + Confirm (btn-danger / btn-primary).
// Theme-aware via theme.css vars — works in light + dark with no extra work.
//
// Variants (Figma: ModalDelete / ModalConfirm / ModalDiscard):
//   tone="danger"  → hard deletes (red solid confirm)
//   tone="primary" → reversible confirms: hide/unhide, status change, send
//   tone="neutral" → discard-unsaved-changes (both buttons outline-ish)
import React, { useEffect, useRef } from 'react';
import { AlertTriangle, Loader, Trash2, Info } from 'lucide-react';

const TONE = {
  danger: {
    icon: Trash2,
    iconClass: 'text-destructive',
    confirmClass:
      'px-4 py-2 bg-destructive text-white rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-60 flex items-center gap-2',
  },
  primary: {
    icon: Info,
    iconClass: 'text-primary',
    confirmClass:
      'px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary-hover transition disabled:opacity-60 flex items-center gap-2',
  },
  neutral: {
    icon: AlertTriangle,
    iconClass: 'text-warning',
    confirmClass:
      'px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary-hover transition disabled:opacity-60 flex items-center gap-2',
  },
};

const ConfirmDialog = ({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  busy = false,
  icon: IconProp,
  onConfirm,
  onClose,
}) => {
  const confirmRef = useRef(null);
  const prevFocusRef = useRef(null);

  // Esc to close + focus management (shadcn Alert Dialog behavior)
  useEffect(() => {
    if (!open) return;
    prevFocusRef.current = document.activeElement;
    const t = setTimeout(() => confirmRef.current?.focus(), 0);
    const onKey = (e) => {
      if (e.key === 'Escape' && !busy) onClose?.();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      clearTimeout(t);
      prevFocusRef.current?.focus?.();
    };
  }, [open, busy, onClose]);

  if (!open) return null;

  const style = TONE[tone] || TONE.danger;
  const Icon = IconProp || style.icon;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={() => {
        if (!busy) onClose?.();
      }}
    >
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative bg-card rounded-xl shadow-xl border border-border w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
          <Icon size={18} className={style.iconClass} />
          {title}
        </h2>
        {message ? (
          <p className="text-sm text-muted-foreground mt-2 whitespace-pre-line">{message}</p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 border border-input rounded-lg hover:bg-muted transition-colors text-sm font-medium disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={style.confirmClass}
          >
            {busy && <Loader className="animate-spin" size={16} />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
