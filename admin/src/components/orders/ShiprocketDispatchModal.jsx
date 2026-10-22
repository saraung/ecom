import React, { useState, useEffect } from 'react';
import { 
  X, 
  Truck, 
  MapPin, 
  RefreshCw,
  Zap
} from 'lucide-react';
import { 
  checkShippingServiceability, 
  createShiprocketOrder, 
  assignOrderAWB 
} from '../../api/orders';
import toast from 'react-hot-toast';
import { formatPrice } from '../../utils/format';

const ShiprocketDispatchModal = ({ isOpen, onClose, order, onSuccess }) => {
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [couriers, setCouriers] = useState([]);
  const [selectedCourier, setSelectedCourier] = useState(null);
  const [pincodeInfo, setPincodeInfo] = useState({ pickup: '', delivery: '' });

  useEffect(() => {
    if (isOpen && order) {
      loadCouriers();
    }
  }, [isOpen, order]);

  const loadCouriers = async () => {
    try {
      setLoading(true);
      const res = await checkShippingServiceability(order.id);
      setCouriers(res.data.available_couriers || []);
      setPincodeInfo({
        pickup: res.data.pickup_pincode,
        delivery: res.data.delivery_pincode
      });
      if (res.data.available_couriers?.length > 0) {
        setSelectedCourier(res.data.available_couriers[0].courier_company_id);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to fetch available couriers');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAndAssign = async () => {
    try {
      setProcessing(true);
      await createShiprocketOrder(order.id);
      toast.success('Shipment registered with Shiprocket');
      // Forward the selected courier's ETD so the backend can persist the
      // ETA date ("Arriving by …") at assignment time.
      const selected = couriers.find((ct) => ct.courier_company_id === selectedCourier);
      await assignOrderAWB(order.id, selectedCourier, selected?.etd);
      toast.success('AWB code generated successfully!');
      if (onSuccess) onSuccess();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to dispatch shipment');
    } finally {
      setProcessing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-card w-full max-w-lg rounded-2xl border border-border shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="p-4 sm:p-5 border-b border-border flex items-center justify-between bg-muted/40">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-purple-500/15 text-purple-600 dark:text-purple-400">
              <Truck size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-foreground text-base">Ship with Shiprocket</h3>
              <p className="text-xs text-muted-foreground">Select courier partner for Order #{order?.order_number}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4">
          <div className="flex items-center justify-between bg-muted/40 p-3 rounded-xl border border-border text-xs">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <MapPin size={14} className="text-primary" />
              Pickup: <b>{pincodeInfo.pickup || '110001'}</b>
            </div>
            <span>➔</span>
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <MapPin size={14} className="text-primary" />
              Delivery: <b>{order?.shipping_address?.postal_code || pincodeInfo.delivery}</b>
            </div>
          </div>

          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Available Courier Partners
          </h4>

          {loading ? (
            <div className="py-12 text-center text-muted-foreground text-sm flex items-center justify-center gap-2">
              <RefreshCw size={18} className="animate-spin text-primary" />
              Checking courier rates & serviceability...
            </div>
          ) : couriers.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted-foreground">
              No couriers serviceable for this destination pincode.
            </div>
          ) : (
            <div className="space-y-2.5">
              {couriers.map((c) => {
                const isSelected = selectedCourier === c.courier_company_id;
                return (
                  <div
                    key={c.courier_company_id}
                    onClick={() => setSelectedCourier(c.courier_company_id)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between ${
                      isSelected 
                        ? 'border-primary bg-primary/5 shadow-sm ring-1 ring-primary' 
                        : 'border-border hover:border-border/80 hover:bg-muted/30'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${
                        isSelected ? 'border-primary bg-primary' : 'border-muted-foreground'
                      }`}>
                        {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                      </div>
                      <div>
                        <div className="font-semibold text-sm text-foreground">{c.courier_name}</div>
                        <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                          <span>Est: {c.etd}</span>
                          <span>•</span>
                          <span>⭐ {c.rating}</span>
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="font-bold text-sm text-foreground">{formatPrice(c.rate)}</div>
                      <span className="text-[10px] text-muted-foreground">Shipping fee</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border bg-muted/20 flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            disabled={loading || processing || !selectedCourier}
            onClick={handleCreateAndAssign}
            className="flex items-center gap-2 px-5 py-2 text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg shadow-sm disabled:opacity-50 transition-all"
          >
            {processing ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                Generating AWB...
              </>
            ) : (
              <>
                <Zap size={14} />
                Generate AWB & Dispatch
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ShiprocketDispatchModal;

