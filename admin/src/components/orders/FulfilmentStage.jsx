/**
 * FulfilmentStage — a compact progress rail for a parcel's shipping journey.
 *
 * The backend computes the stage (`shipment_stage` on the order payload); this
 * component only renders it. Keeping the derivation server-side means the
 * progress bar, the status pill and the simulator can never disagree about what
 * state a parcel is in.
 *
 * Off-happy-path parcels (returned / cancelled / delivery issue) have no step
 * and deliberately render as a warning state instead of a progress bar — a
 * returned parcel at "step 3 of 5" would be actively misleading.
 */
import React from 'react';
import { AlertTriangle, Undo2, CheckCircle2 } from 'lucide-react';
import { FULFILMENT_TRACK, STAGE_TONE_CLASSES } from '../../api/orders';

const OFF_PATH = {
  returned: { Icon: Undo2, hint: 'Parcel returned to warehouse' },
  exception: { Icon: AlertTriangle, hint: 'Courier reported a problem — review required' },
  cancelled: { Icon: AlertTriangle, hint: 'Shipment was cancelled' },
};

const FulfilmentStage = ({ stage, showRail = true, compact = false }) => {
  if (!stage) return null;

  const tone = STAGE_TONE_CLASSES[stage.tone] || STAGE_TONE_CLASSES.neutral;
  const offPath = OFF_PATH[stage.stage];

  // Exception / returned / cancelled: no progress bar, state the problem.
  if (offPath) {
    const { Icon, hint } = offPath;
    return (
      <div>
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${tone}`}
        >
          <Icon size={12} />
          {stage.label}
        </span>
        {!compact && <p className="text-[11px] text-muted-foreground mt-1">{hint}</p>}
        {stage.raw_status && (
          <p className="text-[11px] text-muted-foreground mt-0.5 font-mono">
            Courier reported: {stage.raw_status}
          </p>
        )}
      </div>
    );
  }

  const currentStep = stage.step ?? 0;

  return (
    <div>
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${tone}`}
      >
        {stage.stage === 'delivered' && <CheckCircle2 size={12} />}
        {stage.label}
      </span>

      {showRail && currentStep > 0 && (
      <div className="mt-2" role="list" aria-label="Shipping progress">
        <div className="grid grid-cols-5 gap-1">
          {FULFILMENT_TRACK.map((t) => {
            const done = currentStep >= t.step;
            const isCurrent = currentStep === t.step;
            return (
              <div key={t.key} role="listitem" className="min-w-0">
                <div
                  className={`h-1.5 rounded-full transition-colors ${
                    done ? 'bg-primary' : 'bg-muted'
                  } ${isCurrent ? 'ring-2 ring-primary/30' : ''}`}
                />
                {!compact && (
                  <p
                    className={`mt-1 h-7 text-[10px] leading-tight text-center overflow-hidden ${
                      isCurrent
                        ? 'text-foreground font-semibold'
                        : done
                        ? 'text-muted-foreground'
                        : 'text-muted-foreground/60'
                    }`}
                  >
                    {t.label}
                  </p>
                )}
              </div>
            );
          })}
        </div>
        {stage.raw_status && stage.raw_status !== stage.label.toUpperCase() && (
          <p className="text-[11px] text-muted-foreground mt-1 font-mono truncate">
            Courier: {stage.raw_status}
          </p>
        )}
      </div>
      )}
    </div>
  );
};

export default FulfilmentStage;
