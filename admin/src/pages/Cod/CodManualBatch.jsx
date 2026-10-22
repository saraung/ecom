// src/pages/Cod/CodManualBatch.jsx
/**
 * Manual COD remittance batch entry — for when the finance team has the CRF
 * details but no usable CSV export. Matching still happens server-side.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader, Plus, Save, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { createManualCodRemittance } from '../../api/cod';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import {
  apiErrorMessage,
  buildManualPayload,
  emptyManualRow,
  todayInputValue,
  validateManualForm,
} from '../../utils/cod';

const CodManualBatch = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const allowed = canDo(user, 'cod.reconcile', 'manager');

  const [crfId, setCrfId] = useState('');
  const [remittanceDate, setRemittanceDate] = useState(todayInputValue());
  const [notes, setNotes] = useState('');
  const [rows, setRows] = useState([{ ...emptyManualRow() }]);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState([]);

  const updateRow = (index, field, value) => {
    setRows((current) => current.map((row, rowIndex) => {
      if (rowIndex !== index) return row;
      const next = { ...row, [field]: value };
      if (field === 'cod_amount' || field === 'deductions') {
        const cod = Number(next.cod_amount);
        const deductions = Number(next.deductions || 0);
        if (next.cod_amount !== '' && Number.isFinite(cod) && Number.isFinite(deductions)) {
          next.net_amount = (cod - deductions).toFixed(2);
        }
      }
      return next;
    }));
  };

  const addRow = () => setRows((current) => [...current, { ...emptyManualRow() }]);
  const removeRow = (index) => {
    setRows((current) => (current.length === 1 ? current : current.filter((_, i) => i !== index)));
  };

  const submit = async (event) => {
    event.preventDefault();
    const nextErrors = validateManualForm({ crfId, remittanceDate, rows });
    setErrors(nextErrors);
    if (nextErrors.length) return;
    try {
      setSaving(true);
      const response = await createManualCodRemittance(
        buildManualPayload({ crfId, remittanceDate, notes, rows })
      );
      toast.success('Manual remittance batch created');
      navigate(`/cod/${response.data.id}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not create this batch'));
    } finally {
      setSaving(false);
    }
  };

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to create COD remittances.
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <div>
        <button
          type="button"
          onClick={() => navigate('/cod')}
          className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-2"
        >
          <ArrowLeft size={14} /> Back to COD reconciliation
        </button>
        <h1 className="text-xl sm:text-2xl font-bold text-foreground">New manual COD batch</h1>
        <p className="text-sm text-muted-foreground">
          Use this when you know the CRF / payout details. Totals are recomputed from the lines on save; the
          server matches each AWB or order number before allocating anything.
        </p>
      </div>

      <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-xs font-medium text-muted-foreground">
            CRF / batch reference
            <input
              type="text"
              value={crfId}
              onChange={(event) => setCrfId(event.target.value)}
              placeholder="e.g. CRF-MANUAL-001"
              className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
            />
          </label>
          <label className="text-xs font-medium text-muted-foreground">
            Remittance date
            <input
              type="date"
              value={remittanceDate}
              onChange={(event) => setRemittanceDate(event.target.value)}
              className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
            />
          </label>
          <label className="text-xs font-medium text-muted-foreground sm:col-span-2">
            Notes (optional)
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={2}
              className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
            />
          </label>
        </div>
      </div>

      <div className="bg-card rounded-xl shadow-sm border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold text-foreground">Remittance lines</h2>
            <p className="text-xs text-muted-foreground">
              Enter an AWB or order number per line. Net can be left blank and is derived from COD − deductions.
            </p>
          </div>
          <button
            type="button"
            onClick={addRow}
            className="px-2.5 py-1.5 border border-input rounded-lg text-xs inline-flex items-center gap-1 hover:bg-muted"
          >
            <Plus size={13} /> Add line
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px]">
            <thead className="bg-muted">
              <tr>
                {['AWB', 'Order number', 'COD amount', 'Deductions', 'Net amount', ''].map((label) => (
                  <th key={label || 'remove'} className="px-3 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((row, index) => (
                <tr key={index}>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      value={row.awb}
                      onChange={(event) => updateRow(index, 'awb', event.target.value)}
                      placeholder="AWB"
                      className="w-full px-2.5 py-2 border border-input rounded-lg text-sm bg-card"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      value={row.order_number}
                      onChange={(event) => updateRow(index, 'order_number', event.target.value)}
                      placeholder="Order number"
                      className="w-full px-2.5 py-2 border border-input rounded-lg text-sm bg-card"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={row.cod_amount}
                      onChange={(event) => updateRow(index, 'cod_amount', event.target.value)}
                      className="w-32 px-2.5 py-2 border border-input rounded-lg text-sm bg-card"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={row.deductions}
                      onChange={(event) => updateRow(index, 'deductions', event.target.value)}
                      className="w-28 px-2.5 py-2 border border-input rounded-lg text-sm bg-card"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={row.net_amount}
                      onChange={(event) => updateRow(index, 'net_amount', event.target.value)}
                      className="w-32 px-2.5 py-2 border border-input rounded-lg text-sm bg-card"
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => removeRow(index)}
                      disabled={rows.length === 1}
                      className="p-2 rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-30"
                      aria-label={`Remove line ${index + 1}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {errors.length > 0 && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
          <p className="text-sm font-medium text-destructive mb-1">Check these before saving:</p>
          <ul className="list-disc list-inside text-xs text-destructive space-y-0.5">
            {errors.map((error) => <li key={error}>{error}</li>)}
          </ul>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          The batch starts as <strong>awaiting bank credit</strong>. No payment is created here.
        </p>
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium inline-flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {saving ? <Loader size={15} className="animate-spin" /> : <Save size={15} />}
          Create batch
        </button>
      </div>
    </form>
  );
};

export default CodManualBatch;
