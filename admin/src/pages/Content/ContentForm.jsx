// src/pages/Content/ContentForm.jsx
/**
 * Content block create/edit page (requires content.manage).
 *
 * Full-page form like Product/Category/Coupon forms — the modal got too
 * cramped for image upload + scheduling + preview. Edit loads the block
 * via GET /admin/content/blocks/:id; save returns to /content.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save, RefreshCw, Upload, Megaphone, Inbox, Monitor, Smartphone } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getContentBlock,
  createContentBlock,
  updateContentBlock,
  uploadContentImage,
} from '../../api/content';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import PageSkeleton from '../../components/ui/PageSkeleton';

const KNOWN_KEYS = [
  { key: 'announcement.bar', desc: 'Thin strip above the storefront header' },
  { key: 'home.hero', desc: 'Homepage headline + subcopy + CTA' },
];

// Per-slot image rules (mirrors the backend SLOT_IMAGE_SPECS).
const SLOT_IMAGE_SPECS = {
  'announcement.bar': {
    maxBytes: 1_000_000,
    aspect: 10 / 1,
    label: '800 × 80 px (10:1), ≤1 MB',
  },
  'home.hero': {
    maxBytes: 5_000_000,
    aspect: 3 / 2,
    label: '1440 × 960 px (3:2), ≤5 MB — split hero',
  },
  'home.hero.overlay': {
    maxBytes: 5_000_000,
    aspect: 16 / 6,
    label: '1920 × 720 px (16:6), ≤5 MB — full image',
  },
  'home.hero.mobile': {
    maxBytes: 5_000_000,
    aspect: 4 / 5,
    label: '900 × 1125 px (4:5), ≤5 MB — mobile',
  },
};
const DEFAULT_IMAGE_SPEC = { maxBytes: 5_000_000, aspect: null, label: '≤5 MB' };
const specFor = (key, layoutMode = 'split') => {
  if (key === 'home.hero' && layoutMode !== 'split') return SLOT_IMAGE_SPECS['home.hero.overlay'];
  return SLOT_IMAGE_SPECS[key] || DEFAULT_IMAGE_SPEC;
};

const emptyForm = {
  key: '',
  title: '',
  body: '',
  layout_mode: 'split',
  image_url: '',
  image_public_id: '',
  mobile_image_url: '',
  mobile_image_public_id: '',
  image_alt: '',
  image_position: 'center',
  link: '',
  link_label: '',
  sort_order: '0',
  is_active: true,
  starts_at: '',
  ends_at: '',
};

const toForm = (block) => ({
  key: block?.key || '',
  title: block?.title || '',
  body: block?.body || '',
  layout_mode: block?.layout_mode || 'overlay',
  image_url: block?.image_url || '',
  image_public_id: block?.image_public_id || '',
  mobile_image_url: block?.mobile_image_url || '',
  mobile_image_public_id: block?.mobile_image_public_id || '',
  image_alt: block?.image_alt || '',
  image_position: block?.image_position || 'center',
  link: block?.link || '',
  link_label: block?.link_label || '',
  sort_order: String(block?.sort_order ?? 0),
  is_active: block?.is_active ?? true,
  starts_at: block?.starts_at ? block.starts_at.slice(0, 16) : '',
  ends_at: block?.ends_at ? block.ends_at.slice(0, 16) : '',
});

const inputClass =
  'w-full px-3 py-2 border border-input rounded-lg text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary';
const labelClass = 'block text-sm font-medium text-foreground mb-1';

const HeroBannerPreview = ({ form, device }) => {
  const mobile = device === 'mobile';
  const imageUrl = mobile ? (form.mobile_image_url || form.image_url) : form.image_url;
  const position = {
    center: 'center',
    top: 'center top',
    bottom: 'center bottom',
    left: 'left center',
    right: 'right center',
  }[form.image_position] || 'center';
  const frameClass = mobile
    ? 'mx-auto aspect-[4/5] w-full max-w-[260px]'
    : 'aspect-[16/6]';
  const ctaLabel = form.link_label.trim() || 'Shop Collection';
  const previewFrame = 'relative isolate @container overflow-hidden rounded-xl';
  const kickerClass = mobile
    ? 'mb-[2.8cqw] text-[clamp(6px,2.83cqw,9px)]'
    : 'mb-[1.25cqw] text-[clamp(7px,0.78cqw,10px)]';
  const headingClass = mobile
    ? 'line-clamp-3 text-[clamp(12px,7.55cqw,24px)]'
    : 'text-[clamp(12px,4.7cqw,60px)]';
  const bodyClass = mobile
    ? 'mt-[2cqw] line-clamp-2 text-[clamp(9px,3.77cqw,12px)]'
    : 'mt-[1.25cqw] text-[clamp(10px,1.25cqw,16px)]';
  const ctaClass = mobile
    ? 'mt-[3cqw] px-[6.3cqw] py-[2.5cqw] text-[clamp(7px,3.14cqw,10px)]'
    : 'mt-[2.2cqw] px-[2.2cqw] py-[1.1cqw] text-[clamp(7px,0.94cqw,12px)]';

  const Copy = ({ inverted = false }) => (
    <div className={`flex min-h-0 flex-col items-start justify-center overflow-hidden ${mobile ? 'px-[7.55cqw] py-[2cqw]' : 'px-[5cqw] py-[3cqw]'}`}>
      <p className={`${kickerClass} font-bold uppercase tracking-[0.22em] ${inverted ? 'text-white/80' : 'text-accent'}`}>A considered collection</p>
      <p className={`${headingClass} text-balance font-extrabold leading-[0.98] tracking-[-0.055em] ${inverted ? 'text-white' : 'text-foreground'}`}>
        {form.title || 'Banner headline'}
      </p>
      {form.body && (
        <p className={`${bodyClass} max-w-lg leading-relaxed ${inverted ? 'text-white/90' : 'text-muted-foreground'}`}>
          {form.body}
        </p>
      )}
      {form.layout_mode !== 'artwork' && (
        <span className={`${ctaClass} inline-flex w-fit items-center justify-center rounded-full bg-primary font-bold uppercase tracking-widest text-primary-foreground`}>
          {ctaLabel}
        </span>
      )}
    </div>
  );

  if (form.layout_mode === 'artwork') {
    return (
      <div className={`${previewFrame} bg-muted ${frameClass}`}>
        {imageUrl ? (
          <img src={imageUrl} alt={form.image_alt || ''} className="absolute inset-0 h-full w-full object-contain" style={{ objectPosition: position }} />
        ) : <div className="absolute inset-0 grid place-items-center text-xs text-muted-foreground">Upload finished artwork</div>}
      </div>
    );
  }

  if (form.layout_mode === 'overlay') {
    return (
      <div className={`${previewFrame} bg-neutral-900 ${frameClass}`}>
        {imageUrl && <img src={imageUrl} alt="" className="absolute inset-0 h-full w-full object-cover" style={{ objectPosition: position }} />}
        <div className="absolute inset-0 bg-gradient-to-r from-black/75 via-black/45 to-black/10" />
        <div className="absolute inset-0 flex flex-col items-start justify-center text-white">
          <Copy inverted />
        </div>
      </div>
    );
  }

  return (
    <div className={`${previewFrame} grid bg-background ${mobile ? 'grid-cols-1 grid-rows-[55%_45%]' : 'grid-cols-[.9fr_1.1fr]'} ${frameClass}`}>
      <div className="relative z-10 min-h-0 overflow-hidden bg-muted">
        <Copy />
      </div>
      <div className="relative min-h-0 overflow-hidden bg-primary-soft">
        {imageUrl ? (
          <img src={imageUrl} alt="" className="absolute inset-0 h-full w-full object-cover" style={{ objectPosition: position }} />
        ) : <span className="absolute inset-0 grid place-items-center text-[9px] text-muted-foreground">Add a lifestyle photo</span>}
      </div>
    </div>
  );
};

const ContentForm = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const { user } = useAuth();
  const isEdit = !!id;
  // Matches the backend require_perm("content.manage"). Returned below,
  // after every hook (Rules of Hooks).
  const allowed = canDo(user, 'content.manage', 'manager');

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadNote, setUploadNote] = useState('');
  const [previewDevice, setPreviewDevice] = useState('desktop');
  const [form, setForm] = useState(emptyForm);

  useEffect(() => {
    if (isEdit && allowed) {
      const fetchBlock = async () => {
        try {
          setLoading(true);
          const res = await getContentBlock(id);
          setForm(toForm(res.data));
        } catch {
          toast.error('Failed to load content block');
          navigate('/content');
        } finally {
          setLoading(false);
        }
      };
      fetchBlock();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, allowed]);

  const slotKey = form.key.trim().toLowerCase();
  const activeSpec = specFor(slotKey, form.layout_mode);
  const isHomeHero = slotKey === 'home.hero';
  const knownSlot = isEdit
    ? null
    : KNOWN_KEYS.find((k) => k.key === slotKey);

  const handleFileSelect = async (event, variant = 'desktop') => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const isMobile = variant === 'mobile';
    const urlField = isMobile ? 'mobile_image_url' : 'image_url';
    const publicIdField = isMobile ? 'mobile_image_public_id' : 'image_public_id';
    const uploadSlot = isMobile
      ? 'home.hero.mobile'
      : (slotKey === 'home.hero' && form.layout_mode !== 'split' ? 'home.hero.overlay' : slotKey);
    const spec = specFor(uploadSlot, form.layout_mode);

    if (file.size > spec.maxBytes) {
      setUploadNote(
        `Too big: ${(file.size / 1_000_000).toFixed(1)} MB — this slot caps at ${spec.label}.`
      );
      return;
    }
    if (!file.type.startsWith('image/')) {
      setUploadNote('That file is not an image.');
      return;
    }
    const dims = await new Promise((resolve) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        resolve({ w: img.naturalWidth, h: img.naturalHeight });
        URL.revokeObjectURL(url);
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        resolve(null);
      };
      img.src = url;
    });
    if (!dims) {
      setUploadNote('Could not read that image — try another file.');
      return;
    }
    if (spec.aspect) {
      const drift = Math.abs(dims.w / dims.h - spec.aspect) / spec.aspect;
      if (drift > 0.1) {
        setUploadNote(
          `Heads up: ${dims.w}×${dims.h} vs recommended ${spec.label} — it will be cropped to fit.`
        );
      } else {
        setUploadNote('');
      }
    } else {
      setUploadNote('');
    }

    try {
      setUploading(true);
      const res = await uploadContentImage(uploadSlot || '', file);
      setForm((prev) => ({ ...prev, [urlField]: res.data?.url || '', [publicIdField]: res.data?.public_id || '' }));
      const serverWarn = res.data?.aspect_warning;
      if (serverWarn) setUploadNote(serverWarn);
      toast.success('Image uploaded');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setUploadNote(typeof detail === 'string' ? detail : 'Upload failed — try a smaller image.');
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (uploading) return;
    if (!isEdit && !form.key.trim()) {
      toast.error('Slot key is required');
      return;
    }
    if (!form.title.trim()) {
      toast.error('Title is required');
      return;
    }
    if (isHomeHero && form.layout_mode === 'artwork' && !form.image_url.trim()) {
      toast.error('Upload the finished artwork image first');
      return;
    }
    if (isHomeHero && form.layout_mode === 'artwork' && !form.image_alt.trim()) {
      toast.error('Add alt text describing the artwork and its promotion');
      return;
    }
    if (form.starts_at && form.ends_at && new Date(form.ends_at) <= new Date(form.starts_at)) {
      toast.error('End must be after start');
      return;
    }
    const payload = {
      title: form.title.trim(),
      body: form.body.trim() || null,
      layout_mode: isHomeHero ? form.layout_mode : 'split',
      image_url: form.image_url.trim() || null,
      image_public_id: form.image_public_id.trim() || null,
      mobile_image_url: isHomeHero ? (form.mobile_image_url.trim() || null) : null,
      mobile_image_public_id: isHomeHero ? (form.mobile_image_public_id.trim() || null) : null,
      image_alt: isHomeHero ? (form.image_alt.trim() || null) : null,
      image_position: isHomeHero ? form.image_position : 'center',
      link: form.link.trim() || null,
      link_label: form.link_label.trim() || null,
      sort_order: Math.max(0, Math.min(999, parseInt(form.sort_order, 10) || 0)),
      is_active: form.is_active,
      starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
      ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
    };
    try {
      setSaving(true);
      if (isEdit) {
        await updateContentBlock(id, payload);
        toast.success('Content block updated');
      } else {
        await createContentBlock({ key: form.key.trim().toLowerCase(), ...payload });
        toast.success('Content block created');
      }
      navigate('/content');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not save content block');
    } finally {
      setSaving(false);
    }
  };

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to manage content.
      </div>
    );
  }

  if (loading) return <PageSkeleton type="content-form" title={isEdit ? 'Edit Banner' : 'New Banner'} />;

  return (
    // Full-width (no max-w-* wrapper) like ProductForm so the 3-column
    // layout fills the viewport instead of leaving the right side empty.
    <div>
      <button
        type="button"
        onClick={() => navigate('/content')}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-3"
      >
        <ArrowLeft size={15} />
        Back to Banners
      </button>
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 mb-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">
            {isEdit ? 'Edit Banner' : 'New Banner'}
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {isEdit
              ? 'Changes go live on the storefront immediately after saving.'
              : 'Pick a slot, compose, schedule — live on save.'}
          </p>
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          <button
            type="button"
            onClick={() => navigate('/content')}
            className="flex-1 sm:flex-none px-4 py-2.5 sm:py-2 border border-input rounded-lg text-sm hover:bg-muted transition text-center"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || uploading}
            onClick={handleSave}
            className="flex-1 sm:flex-none px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium flex items-center justify-center gap-1 hover:bg-primary-hover transition disabled:opacity-60"
          >
            {saving ? (
              <>
                <RefreshCw size={15} className="animate-spin" />
                Saving…
              </>
            ) : (
              <>
                <Save size={15} />
                {isEdit ? 'Save changes' : 'Create banner'}
              </>
            )}
          </button>
        </div>
      </div>

      <form onSubmit={handleSave} className="grid grid-cols-1 lg:grid-cols-3 gap-3 items-start lg:items-stretch">
        {/* Left: compose */}
        <div className="bg-card rounded-xl border border-border p-4 space-y-3 lg:col-span-1">
          <h2 className="text-sm font-semibold text-foreground">Compose</h2>
          {!isEdit && (
            <div>
              <label htmlFor="block-key" className={labelClass}>
                Slot key <span className="text-destructive">*</span>
              </label>
              <input
                id="block-key"
                type="text"
                value={form.key}
                onChange={(e) => setForm({ ...form, key: e.target.value.toLowerCase() })}
                placeholder="announcement.bar"
                pattern="^[a-z0-9._-]+$"
                className={`${inputClass} font-mono`}
              />
              <p className="text-xs text-muted-foreground mt-1">
                {KNOWN_KEYS.map((k) => (
                  <button
                    key={k.key}
                    type="button"
                    title={k.desc}
                    onClick={() => setForm({ ...form, key: k.key })}
                    className="font-mono text-primary hover:underline mr-2"
                  >
                    {k.key}
                  </button>
                ))}
                {knownSlot && (
                  <span className="block mt-1 text-muted-foreground">{knownSlot.desc}</span>
                )}
              </p>
            </div>
          )}
          <div>
            <label htmlFor="block-title" className={labelClass}>
              Title <span className="text-destructive">*</span>
            </label>
            <input
              id="block-title"
              type="text"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Diwali Sale is live!"
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="block-body" className={labelClass}>
              Body
            </label>
            <textarea
              id="block-body"
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
              rows={2}
              placeholder="Flat 25% off sitewide this weekend…"
              className={`${inputClass} resize-none`}
            />
          </div>
          {isHomeHero && (
            <div>
              <label htmlFor="hero-layout" className={labelClass}>Hero layout</label>
              <select
                id="hero-layout"
                value={form.layout_mode}
                onChange={(e) => setForm({ ...form, layout_mode: e.target.value })}
                className={inputClass}
              >
                <option value="split">Editorial split — copy beside photo</option>
                <option value="overlay">Photo background — live copy over image</option>
                <option value="artwork">Finished artwork — graphic includes copy</option>
              </select>
              <p className="mt-1 text-xs text-muted-foreground">
                Split keeps copy readable with any photo. Artwork needs descriptive alt text.
              </p>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="block-link" className={labelClass}>
                Link
              </label>
              <input
                id="block-link"
                type="text"
                value={form.link}
                onChange={(e) => setForm({ ...form, link: e.target.value })}
                placeholder="/products?sale=diwali"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="block-link-label" className={labelClass}>
                Link label
              </label>
              <input
                id="block-link-label"
                type="text"
                value={form.link_label}
                onChange={(e) => setForm({ ...form, link_label: e.target.value })}
                placeholder="Shop now"
                className={inputClass}
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="block-order" className={labelClass}>
                Order in slot
              </label>
              <input
                id="block-order"
                type="number"
                min={0}
                max={999}
                value={form.sort_order}
                onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
                className={inputClass}
              />
            </div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  className="h-4 w-4 accent-primary"
                />
                Active
              </label>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="block-starts" className={labelClass}>
                Publish from
              </label>
              <input
                id="block-starts"
                type="datetime-local"
                value={form.starts_at}
                onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="block-ends" className={labelClass}>
                Expires at
              </label>
              <input
                id="block-ends"
                type="datetime-local"
                value={form.ends_at}
                onChange={(e) => setForm({ ...form, ends_at: e.target.value })}
                className={inputClass}
              />
            </div>
          </div>
        </div>

        {/* Middle: image */}
        <div className="bg-card rounded-xl border border-border p-4 space-y-3 lg:col-span-1">
          <h2 className="text-sm font-semibold text-foreground">
            {isHomeHero ? 'Hero images' : 'Image'} <span className="text-muted-foreground font-normal">(optional)</span>
          </h2>
          <div className="rounded-lg border border-warning/40 bg-warning/10 p-3">
            <p className="text-xs font-semibold text-foreground mb-1.5">
              Desktop image dimensions
            </p>
            <p className="text-xs font-semibold text-foreground">Recommended: {activeSpec.label}</p>
            <p className="text-xs text-muted-foreground mt-1.5">
              The crop preview below shows how the storefront will frame it. Oversize files are rejected; other shapes save with a crop warning.
            </p>
          </div>
          <div className="rounded-lg border border-dashed border-input bg-muted/30 p-3 mt-3">
            <div className="flex flex-wrap items-center gap-2">
              <label className="px-3 py-2 bg-primary-soft text-primary-soft-foreground rounded-lg text-xs font-medium flex items-center gap-1.5 cursor-pointer hover:bg-muted transition">
                <Upload size={13} />
                {uploading ? 'Uploading…' : 'Upload desktop image'}
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  className="sr-only"
                  disabled={uploading}
                  onChange={(event) => handleFileSelect(event, 'desktop')}
                />
              </label>
              {form.image_url.trim() && (
                <button
                  type="button"
                  onClick={() => setForm({ ...form, image_url: '', image_public_id: '' })}
                  className="px-3 py-2 text-xs text-destructive hover:bg-destructive/10 rounded-lg transition"
                >
                  Remove
                </button>
              )}
            </div>
            {uploadNote && (
              <p className="text-xs text-warning mt-2">{uploadNote}</p>
            )}
            <input
              type="text"
              value={form.image_url}
              onChange={(e) => setForm({ ...form, image_url: e.target.value, image_public_id: '' })}
              placeholder="…or paste a desktop image URL"
              className="mt-2 w-full px-3 py-2 border border-input rounded-lg text-xs font-mono bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          {isHomeHero && (
            <>
              <div className="rounded-lg border border-dashed border-input bg-muted/30 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <label className="px-3 py-2 bg-primary-soft text-primary-soft-foreground rounded-lg text-xs font-medium flex items-center gap-1.5 cursor-pointer hover:bg-muted transition">
                    <Upload size={13} />
                    {uploading ? 'Uploading…' : 'Upload mobile crop'}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      className="sr-only"
                      disabled={uploading}
                      onChange={(event) => handleFileSelect(event, 'mobile')}
                    />
                  </label>
                  {form.mobile_image_url.trim() && (
                    <button
                      type="button"
                      onClick={() => setForm({ ...form, mobile_image_url: '', mobile_image_public_id: '' })}
                      className="px-3 py-2 text-xs text-destructive hover:bg-destructive/10 rounded-lg transition"
                    >
                      Remove mobile image
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  value={form.mobile_image_url}
                  onChange={(e) => setForm({ ...form, mobile_image_url: e.target.value, mobile_image_public_id: '' })}
                  placeholder="Optional mobile image URL (4:5 recommended)"
                  className={inputClass + ' mt-2 font-mono text-xs'}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Recommended mobile image: <span className="font-medium text-foreground">900 × 1125 px (4:5)</span>, up to 5 MB. If omitted, the desktop image is used.
                </p>
              </div>
              {form.layout_mode !== 'artwork' && (
                <div>
                  <label htmlFor="hero-image-position" className={labelClass}>Photo focal position</label>
                  <select
                    id="hero-image-position"
                    value={form.image_position}
                    onChange={(e) => setForm({ ...form, image_position: e.target.value })}
                    className={inputClass}
                  >
                    <option value="center">Center</option>
                    <option value="left">Left</option>
                    <option value="right">Right</option>
                    <option value="top">Top</option>
                    <option value="bottom">Bottom</option>
                  </select>
                </div>
              )}
              <div>
                <label htmlFor="hero-image-alt" className={labelClass}>
                  Image description {form.layout_mode === 'artwork' && <span className="text-destructive">(required for artwork)</span>}
                </label>
                <input
                  id="hero-image-alt"
                  type="text"
                  maxLength={500}
                  value={form.image_alt}
                  onChange={(e) => setForm({ ...form, image_alt: e.target.value })}
                  placeholder="Describe the photo; include promo wording if it is embedded"
                  className={inputClass}
                />
              </div>
            </>
          )}
          {!form.image_url.trim() && (
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Inbox size={12} /> No desktop image — the hero will render with copy only.
            </p>
          )}
        </div>

        {/* Right: live preview */}
        <div className="bg-card rounded-xl border border-border p-4 lg:col-span-1 lg:sticky lg:top-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{isHomeHero ? 'Storefront preview' : 'Preview'}</p>
            {isHomeHero && (
              <div className="flex rounded-lg border border-border p-0.5">
                <button
                  type="button"
                  onClick={() => setPreviewDevice('desktop')}
                  aria-pressed={previewDevice === 'desktop'}
                  className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] ${previewDevice === 'desktop' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
                ><Monitor size={12} /> Desktop</button>
                <button
                  type="button"
                  onClick={() => setPreviewDevice('mobile')}
                  aria-pressed={previewDevice === 'mobile'}
                  className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] ${previewDevice === 'mobile' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
                ><Smartphone size={12} /> Mobile</button>
              </div>
            )}
          </div>
          {isHomeHero ? (
            <HeroBannerPreview form={form} device={previewDevice} />
          ) : (
            <div className="flex items-start gap-3">
              <span className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 bg-warning/20 text-warning">
                <Megaphone size={17} />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{form.title.trim() || 'Block title'}</p>
                <p className="text-xs text-muted-foreground line-clamp-2">{form.body.trim() || 'Block body will appear here.'}</p>
                {form.link_label.trim() && <p className="text-xs text-primary font-medium mt-1">{form.link_label.trim()} →</p>}
              </div>
            </div>
          )}
          <div className="mt-3 text-xs text-muted-foreground space-y-1">
            <p>Slot: <span className="font-mono text-foreground">{form.key || '—'}</span></p>
            <p>Order: <span className="text-foreground">#{form.sort_order || 0}</span></p>
            <p>Status: <span className="text-foreground">{form.is_active ? 'Active' : 'Off'}</span></p>
          </div>
        </div>
      </form>
    </div>
  );
};

export default ContentForm;
