// src/pages/Cod/CodImport.jsx
/**
 * CSV import wizard: upload → inspect/override column mapping → preview
 * matching → commit. Parsing, validation and matching are server-side; the
 * preview is read-only and creates nothing.
 */
import React, { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileUp,
  FlaskConical,
  Loader,
  RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  downloadCodFixture,
  downloadCodTemplate,
  importCodRemittance,
  previewCodImport,
  saveBlob,
} from '../../api/cod';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import { formatPrice } from '../../utils/format';
import { apiErrorMessage, todayInputValue } from '../../utils/cod';
import { EmptyState, ItemStatusBadge, SummaryCard } from '../../components/cod/CodShared';

const FIELDS = [
  { key: 'awb', label: 'AWB' },
  { key: 'order_ref', label: 'Order number' },
  { key: 'cod_amount', label: 'COD amount' },
  { key: 'deductions', label: 'Deductions' },
  { key: 'net_amount', label: 'Net amount' },
  { key: 'remitted_amount', label: 'Remitted amount' },
  { key: 'crf_id', label: 'CRF id' },
  { key: 'remittance_date', label: 'Remittance date' },
  { key: 'utr', label: 'UTR' },
];

const CodImport = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const allowed = canDo(user, 'cod.reconcile', 'manager');

  const [file, setFile] = useState(null);
  const [headers, setHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [crfId, setCrfId] = useState('');
  const [remittanceDate, setRemittanceDate] = useState(todayInputValue());
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const previewSeq = useRef(0);

  const applyPreview = useCallback((data) => {
    setPreview(data);
    setHeaders(data.headers || []);
    const next = {};
    for (const field of FIELDS) next[field.key] = data.mapping?.[field.key] || '';
    setMapping(next);
    setPreviewError('');
  }, []);

  const runPreview = useCallback(async (nextFile, nextMapping) => {
    if (!nextFile) return;
    const seq = previewSeq.current + 1;
    previewSeq.current = seq;
    setPreviewing(true);
    setPreviewError('');
    try {
      const response = await previewCodImport(nextFile, nextMapping);
      if (seq === previewSeq.current) applyPreview(response.data);
    } catch (err) {
      if (seq === previewSeq.current) {
        setPreview(null);
        setPreviewError(apiErrorMessage(err, 'Could not preview this CSV'));
      }
    } finally {
      if (seq === previewSeq.current) setPreviewing(false);
    }
  }, [applyPreview]);

  const handleFile = async (event) => {
    const chosen = event.target.files?.[0] || null;
    setFile(chosen);
    setPreview(null);
    setHeaders([]);
    setMapping({});
    if (chosen) await runPreview(chosen, null);
  };

  const handleMapping = async (field, header) => {
    const next = { ...mapping, [field]: header };
    setMapping(next);
    if (file) await runPreview(file, next);
  };

  const download = async (kind) => {
    try {
      const response = kind === 'template' ? await downloadCodTemplate() : await downloadCodFixture();
      saveBlob(response.data, kind === 'template' ? 'cod-remittance-template.csv' : 'SYNTHETIC_cod_remittance_fixture.csv');
      if (kind === 'fixture') toast.success('Synthetic fixture downloaded — not real Shiprocket data');
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Download failed'));
    }
  };

  const commit = async () => {
    if (previewing) {
      toast.error('Wait for the preview refresh to finish');
      return;
    }
    if (!file) {
      toast.error('Choose a CSV file first');
      return;
    }
    if (!crfId.trim()) {
      toast.error('Enter the CRF / batch reference');
      return;
    }
    if (!remittanceDate) {
      toast.error('Choose the remittance date');
      return;
    }
    try {
      setSaving(true);
      const response = await importCodRemittance({
        file,
        crfId: crfId.trim(),
        remittanceDate,
        mapping,
        notes: notes.trim(),
      });
      toast.success('Remittance batch imported');
      navigate(`/cod/${response.data.id}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not import this batch'));
    } finally {
      setSaving(false);
    }
  };

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to import COD remittances.
      </div>
    );
  }

  const summary = preview?.summary;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <button
            type="button"
            onClick={() => navigate('/cod')}
            className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-2"
          >
            <ArrowLeft size={14} /> Back to COD reconciliation
          </button>
          <h1 className="text-xl sm:text-2xl font-bold text-foreground">Import COD remittance CSV</h1>
          <p className="text-sm text-muted-foreground">
            Shiprocket has no COD remittance API. Export the report from the panel (Billing → COD Remittance),
            then upload it here. Nothing is saved until you confirm the final step.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => download('template')}
            className="px-3 py-2 border border-input rounded-lg text-sm flex items-center gap-1.5 hover:bg-muted"
          >
            <Download size={15} /> Blank template
          </button>
          <button
            type="button"
            onClick={() => download('fixture')}
            className="px-3 py-2 border border-input rounded-lg text-sm flex items-center gap-1.5 hover:bg-muted"
          >
            <FlaskConical size={15} /> Synthetic fixture
          </button>
        </div>
      </div>

      <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
        <h2 className="font-semibold text-foreground mb-1">1. Choose the CSV</h2>
        <p className="text-xs text-muted-foreground mb-3">
          The importer auto-detects the usual Shiprocket column names and lets you override every mapping.
        </p>
        <label className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border px-4 py-8 cursor-pointer hover:border-primary/50 transition">
          <FileUp size={26} className="text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">
            {file ? file.name : 'Click to choose a CSV file'}
          </span>
          <span className="text-xs text-muted-foreground">CSV up to 5 MB · UTF-8, Windows-1252 or Latin-1</span>
          <input type="file" accept=".csv,text/csv,text/plain" onChange={handleFile} className="sr-only" />
        </label>
        {file && (
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => runPreview(file, mapping)}
              disabled={previewing}
              className="px-3 py-1.5 border border-input rounded-lg text-xs flex items-center gap-1.5 hover:bg-muted disabled:opacity-50"
            >
              {previewing ? <Loader size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              Refresh preview
            </button>
            {preview && (
              <span className="text-xs text-muted-foreground">
                {preview.rows?.length || 0} row(s) parsed
              </span>
            )}
          </div>
        )}
        {previewError && (
          <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive flex items-start gap-2">
            <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" /> {previewError}
          </div>
        )}
      </div>

      {headers.length > 0 && (
        <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
          <h2 className="font-semibold text-foreground mb-1">2. Column mapping</h2>
          <p className="text-xs text-muted-foreground mb-4">
            Unmapped optional fields are ignored. AWB or order number is required per line; amounts are parsed
            server-side (₹ and thousands separators are fine).
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {FIELDS.map((field) => (
              <label key={field.key} className="text-xs font-medium text-muted-foreground">
                {field.label}
                <select
                  value={mapping[field.key] || ''}
                  onChange={(event) => handleMapping(field.key, event.target.value)}
                  className="mt-1 w-full px-2.5 py-2 border border-input rounded-lg text-sm bg-card text-foreground font-normal"
                >
                  <option value="">Not mapped</option>
                  {headers.map((header) => (
                    <option key={header} value={header}>{header}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </div>
      )}

      {previewing && !preview && (
        <div className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader size={15} className="animate-spin" /> Parsing and matching rows…
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <SummaryCard label="Rows" value={summary.rows} hint="Parsed remittance lines" />
          <SummaryCard label="Matched" value={summary.matched} hint="Ready to allocate" icon={CheckCircle2} tone="text-success" />
          <SummaryCard label="Flagged" value={summary.flagged} hint="Need a decision before confirm" icon={AlertTriangle} tone="text-warning" />
          <SummaryCard label="Net expected" value={formatPrice(summary.net_expected)} hint="After listed deductions" />
        </div>
      )}

      {preview && (
        <div className="bg-card rounded-xl shadow-sm border border-border overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="font-semibold text-foreground">3. Preview matching</h2>
            <p className="text-xs text-muted-foreground">
              Nothing has been saved. Flagged rows can still be imported; confirm is blocked until every flag is
              accepted or excluded on the batch page.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px]">
              <thead className="bg-muted">
                <tr>
                  {['Row', 'AWB', 'Order', 'COD', 'Deductions', 'Net', 'Allocate', 'Status / note'].map((label) => (
                    <th key={label} className="px-3 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {preview.rows.map((row) => (
                  <tr key={`${row.row_number}-${row.awb || row.order_ref}`} className="hover:bg-muted/40">
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">{row.row_number}</td>
                    <td className="px-3 py-2.5 text-sm">{row.awb || '—'}</td>
                    <td className="px-3 py-2.5 text-sm">
                      {row.order_number || row.order_ref || '—'}
                      {row.order_status && <div className="text-xs text-muted-foreground">{row.order_status}</div>}
                    </td>
                    <td className="px-3 py-2.5 text-sm">{formatPrice(row.cod_amount)}</td>
                    <td className="px-3 py-2.5 text-sm text-muted-foreground">{formatPrice(row.deductions)}</td>
                    <td className="px-3 py-2.5 text-sm">{formatPrice(row.net_amount)}</td>
                    <td className="px-3 py-2.5 text-sm font-medium">{formatPrice(row.remitted_amount)}</td>
                    <td className="px-3 py-2.5 max-w-xs">
                      <ItemStatusBadge status={row.match_status} />
                      {row.match_note && <p className="text-xs text-muted-foreground mt-1">{row.match_note}</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.rows.length === 0 && <EmptyState title="No remittance lines found" />}
        </div>
      )}

      <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
        <h2 className="font-semibold text-foreground mb-1">4. Batch details and import</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Import protection is by CRF / batch reference: importing the same reference twice is rejected. Lines that
          already belong to an in-flight batch are flagged instead of double-counted.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-xs font-medium text-muted-foreground">
            CRF / batch reference
            <input
              type="text"
              value={crfId}
              onChange={(event) => setCrfId(event.target.value)}
              placeholder="e.g. CRF-2026-10-001"
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
              placeholder="Anything the finance team should know about this batch"
              className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
            />
          </label>
        </div>
        <div className="mt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            The batch is created as <strong>awaiting bank credit</strong>; confirming the UTR is a separate step.
          </p>
          <button
            type="button"
            onClick={commit}
            disabled={saving || previewing || !file || !preview}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium inline-flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {saving ? <Loader size={15} className="animate-spin" /> : <FileUp size={15} />}
            Import batch
          </button>
        </div>
      </div>
    </div>
  );
};

export default CodImport;
