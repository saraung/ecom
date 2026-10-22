// src/components/cod/CodShared.jsx
// Small presentation helpers shared by the COD reconciliation screens.
import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { batchBadgeClass, batchStatusLabel, itemBadgeClass, itemStatusLabel } from '../../utils/cod';

export const BatchStatusBadge = ({ status }) => (
  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap ${batchBadgeClass(status)}`}>
    {batchStatusLabel(status)}
  </span>
);

export const ItemStatusBadge = ({ status }) => (
  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap ${itemBadgeClass(status)}`}>
    {itemStatusLabel(status)}
  </span>
);

export const SourceBadge = ({ source, synthetic }) => {
  if (synthetic) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-warning/15 text-warning border border-warning/30">
        SYNTHETIC — not Shiprocket data
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-muted text-muted-foreground">
      {source === 'csv' ? 'CSV import' : source === 'simulator' ? 'Simulator' : 'Manual entry'}
    </span>
  );
};

export const SummaryCard = ({ label, value, hint, icon: Icon, tone = 'text-primary' }) => (
  <div className="bg-card rounded-xl shadow-sm border border-border p-4">
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="text-xs sm:text-sm text-muted-foreground font-medium">{label}</p>
        <p className="text-lg sm:text-2xl font-bold text-foreground mt-1 break-words">{value}</p>
        {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
      </div>
      {Icon && (
        <div className={`p-2 rounded-lg bg-muted ${tone} flex-shrink-0`}>
          <Icon size={18} />
        </div>
      )}
    </div>
  </div>
);

export const Modal = ({ open, title, subtitle, children, onClose, wide = false }) => {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative bg-card rounded-xl shadow-xl border border-border w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} max-h-[90vh] overflow-y-auto p-5 sm:p-6`}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-foreground">{title}</h2>
            {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

export const EmptyState = ({ title, hint }) => (
  <div className="px-4 py-12 text-center">
    <p className="text-sm font-medium text-foreground">{title}</p>
    {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
  </div>
);
