import React, { useState, useEffect } from 'react';
import {
  X,
  Truck,
  Clock,
  MapPin,
  RefreshCw
} from 'lucide-react';
import { getOrderShippingTracking } from '../../api/orders';
import FulfilmentStage from './FulfilmentStage';

const TrackingModal = ({ isOpen, onClose, orderId, orderNumber }) => {
  const [tracking, setTracking] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen && orderId) {
      loadTracking();
    }
  }, [isOpen, orderId]);

  const loadTracking = async () => {
    try {
      setLoading(true);
      const res = await getOrderShippingTracking(orderId);
      setTracking(res.data);
    } catch {
      // keep fallback
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-card w-full max-w-lg rounded-2xl border border-border shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-border flex items-center justify-between bg-muted/40">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              <Truck size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-foreground text-base">Shipment Tracking</h3>
              <p className="text-xs text-muted-foreground">Order #{orderNumber}</p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto space-y-5">
          {loading ? (
            <div className="py-12 text-center text-muted-foreground text-sm flex items-center justify-center gap-2">
              <RefreshCw size={18} className="animate-spin text-primary" />
              Loading real-time tracking scans...
            </div>
          ) : (
            <>
              {/* Courier & AWB Header pill */}
              <div className="p-3.5 bg-muted/50 rounded-xl border border-border flex items-center justify-between">
                <div>
                  <div className="text-xs text-muted-foreground font-medium">Carrier Partner</div>
                  <div className="text-sm font-semibold text-foreground">{tracking?.courier_name || 'Courier not assigned'}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-muted-foreground font-medium">AWB Number</div>
                  <div className="text-sm font-mono font-bold text-primary">{tracking?.awb_code || 'Pending'}</div>
                </div>
              </div>

              {/* Status Banner — driven by the server-computed fulfilment stage
                  so it can never disagree with the order status. */}
              <div className="space-y-2">
                <FulfilmentStage stage={tracking?.stage} />
                {tracking?.raw_status && (
                  <p className="text-[11px] text-muted-foreground font-mono">
                    Courier reported: {tracking.raw_status}
                  </p>
                )}
              </div>

              {/* Timeline Stepper */}
              <div className="space-y-4 pt-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Activity Timeline
                </h4>

                {(!tracking?.scans || tracking.scans.length === 0) ? (
                  <div className="text-center py-6 text-xs text-muted-foreground space-y-1">
                    <p className="font-medium text-foreground">No scans yet</p>
                    <p>
                      {tracking?.stage?.step >= 2
                        ? 'Pickup is scheduled. The first scan appears once the courier collects the parcel.'
                        : 'Scans appear here once the courier picks up the parcel.'}
                    </p>
                  </div>
                ) : (
                  <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
                    {tracking.scans.slice().reverse().map((scan, idx) => (
                      <div key={idx} className="relative group">
                        {/* Dot */}
                        <div className={`absolute -left-6 top-1 w-3 h-3 rounded-full border-2 border-background ${
                          idx === 0 ? 'bg-primary ring-4 ring-primary/20' : 'bg-muted-foreground/60'
                        }`} />
                        <div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-foreground">{scan.activity || scan.status}</span>
                            <span className="text-muted-foreground text-[11px]">{scan.date}</span>
                          </div>
                          {scan.location && (
                            <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                              <MapPin size={11} /> {scan.location}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-muted/20 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium bg-secondary text-secondary-foreground hover:bg-secondary/80 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default TrackingModal;