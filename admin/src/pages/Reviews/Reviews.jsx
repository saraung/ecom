// src/pages/Reviews/Reviews.jsx
/**
 * Review moderation (requires reviews.moderate — admins only).
 *
 * Hide = abuse/spam disappears from the storefront instantly but stays in
 * the DB as the audit trail. Delete = hard removal for content with no
 * record value. Both actions write audit entries (entity "review").
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Star,
  Eye,
  EyeOff,
  Trash2,
  RefreshCw,
  Search,
  Image as ImageIcon,
  Camera,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getAdminReviews,
  setReviewVisibility,
  deleteReview,
} from '../../api/reviews';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ImageLightbox from '../../components/common/ImageLightbox';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatDate } from '../../utils/format';

const ITEMS_PER_PAGE = 15;


const Stars = ({ value }) => (
  <span className="inline-flex items-center gap-0.5" title={`${value} out of 5 stars`}>
    {[1, 2, 3, 4, 5].map((i) => (
      <Star
        key={i}
        size={13}
        className={i <= value ? 'fill-warning text-warning' : 'text-muted-foreground'}
      />
    ))}
  </span>
);

const MAX_INLINE_THUMBS = 3;

const ReviewThumbs = ({ images = [], sizeClass = 'w-10 h-10', onOpen }) => {
  if (!images.length) return null;
  const visible = images.slice(0, MAX_INLINE_THUMBS);
  const remaining = images.length - visible.length;
  return (
    <div className="flex items-center gap-1.5 mt-1.5">
      <Camera size={12} className="text-muted-foreground shrink-0" aria-hidden="true" />
      <div className="flex items-center gap-1.5 flex-wrap">
        {visible.map((img, idx) => (
          <button
            key={img.id || img.secure_url || idx}
            type="button"
            onClick={() => onOpen?.(idx)}
            aria-label={`Open review photo ${idx + 1} of ${images.length}`}
            title={`Photo ${idx + 1} of ${images.length} — click to enlarge`}
            className={`group/thumb relative ${sizeClass} rounded-lg overflow-hidden border border-border bg-muted cursor-zoom-in hover:border-primary hover:scale-105 active:scale-95 transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary`}
          >
            <img
              src={img.secure_url}
              alt={`Customer review photo ${idx + 1}`}
              loading="lazy"
              className="h-full w-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = 'none';
              }}
            />
          </button>
        ))}
        {remaining > 0 && (
          <button
            type="button"
            onClick={() => onOpen?.(visible.length)}
            aria-label={`View ${remaining} more photo${remaining === 1 ? '' : 's'}`}
            title={`View ${remaining} more photo${remaining === 1 ? '' : 's'}`}
            className={`${sizeClass} rounded-lg border border-border bg-muted text-muted-foreground text-xs font-bold hover:border-primary hover:text-foreground transition-colors`}
          >
            +{remaining}
          </button>
        )}
      </div>
      <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
        {images.length} photo{images.length === 1 ? '' : 's'}
      </span>
    </div>
  );
};

const Reviews = () => {
  const { user } = useAuth();
  const allowed = canDo(user, 'reviews.moderate', 'admin');

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [rating, setRating] = useState('');
  const [hidden, setHidden] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [actingId, setActingId] = useState(null);
  const [photosOnly, setPhotosOnly] = useState(false);
  const [lightbox, setLightbox] = useState(null);
  const [confirmState, setConfirmState] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params = { page, limit: ITEMS_PER_PAGE };
      if (rating) params.rating = Number(rating);
      if (hidden === 'hidden') params.hidden = true;
      if (hidden === 'visible') params.hidden = false;
      if (search) params.search = search;
      const res = await getAdminReviews(params);
      setRows(res.data?.items || []);
      setTotal(res.data?.total || 0);
      setTotalPages(res.data?.total_pages || 1);
    } catch {
      toast.error('Failed to load reviews');
      setRows([]);
      setTotal(0);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  }, [page, rating, hidden, search]);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  const resetPage = () => setPage(1);

  const openLightbox = (review, startIndex = 0) => {
    const images = (review.images || [])
      .filter((img) => img?.secure_url)
      .map((img, i) => ({
        src: img.secure_url,
        alt: `Review by ${review.user_full_name || review.user_email || 'customer'} — photo ${i + 1}`,
      }));
    if (!images.length) return;
    setLightbox({
      images,
      index: Math.min(startIndex, images.length - 1),
      title: `Review by ${review.user_full_name || review.user_email || 'Anonymous'} — ${review.product_name || 'product'}`,
    });
  };

  const photoCount = rows.filter((r) => r.images?.length > 0).length;
  const visibleRows = photosOnly ? rows.filter((r) => r.images?.length > 0) : rows;

  const handleVisibility = (review) => {
    setConfirmState({ kind: 'visibility', target: review });
  };

  const handleDelete = (review) => {
    setConfirmState({ kind: 'delete', target: review });
  };

  const runConfirmed = async () => {
    const s = confirmState;
    if (!s) return;
    if (s.kind === 'visibility') {
      const review = s.target;
      const next = !review.is_hidden;
      try {
        setActingId(review.id);
        await setReviewVisibility(review.id, next);
        toast.success(next ? 'Review hidden' : 'Review visible again');
        load();
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Could not update review');
      } finally {
        setActingId(null);
        setConfirmState(null);
      }
    } else {
      const review = s.target;
      try {
        setActingId(review.id);
        await deleteReview(review.id);
        toast.success('Review deleted');
        load();
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Could not delete review');
      } finally {
        setActingId(null);
        setConfirmState(null);
      }
    }
  };

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to moderate reviews.
      </div>
    );
  }

  if (loading) return <PageSkeleton type="reviews" />;

  const actionsFor = (review, compact = false) => (
    <div className={`flex gap-2 ${compact ? '' : 'justify-end'}`}>
      <button
        type="button"
        disabled={actingId === review.id}
        onClick={() => handleVisibility(review)}
        title={review.is_hidden ? 'Unhide on storefront' : 'Hide from storefront'}
        className={`px-3 ${compact ? 'py-2.5 flex-1' : 'py-1'} rounded-lg text-xs font-medium flex items-center justify-center gap-1 disabled:opacity-60 ${
          review.is_hidden
            ? 'bg-success/15 text-success'
            : 'bg-warning/15 text-warning'
        }`}
      >
        {review.is_hidden ? <Eye size={13} /> : <EyeOff size={13} />}
        {review.is_hidden ? 'Unhide' : 'Hide'}
      </button>
      <button
        type="button"
        disabled={actingId === review.id}
        onClick={() => handleDelete(review)}
        title="Permanently delete"
        className={`px-3 ${compact ? 'py-2.5 flex-1' : 'py-1'} rounded-lg text-xs font-medium flex items-center justify-center gap-1 text-destructive hover:bg-destructive/10 disabled:opacity-60 border border-input`}
      >
        <Trash2 size={13} />
        Delete
      </button>
    </div>
  );

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Reviews</h1>
          <p className="text-sm text-muted-foreground">
            {total} review{total === 1 ? '' : 's'} — hidden ones stay on record, off the storefront
            {photoCount > 0 && (
              <span className="inline-flex items-center gap-1 ml-2">
                <ImageIcon size={13} className="text-muted-foreground" aria-hidden="true" />
                {photoCount} with photo{photoCount === 1 ? '' : 's'} on this page
              </span>
            )}
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

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-2 mb-6">
        <div className="relative flex-1 min-w-0">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setSearch(searchInput.trim());
                resetPage();
              }
            }}
            placeholder="Search title, comment, author email…"
            className="w-full pl-9 pr-3 py-2 border border-input rounded-lg text-sm bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <div className="grid grid-cols-2 sm:flex gap-2">
          <select
            value={rating}
            onChange={(e) => { setRating(e.target.value); resetPage(); }}
            className="border border-input rounded-lg px-3 py-2.5 sm:py-2 text-sm bg-card text-foreground min-w-0"
            aria-label="Filter by star rating"
          >
            <option value="">All ratings</option>
            {[5, 4, 3, 2, 1].map((r) => (
              <option key={r} value={r}>{r} star{r === 1 ? '' : 's'}</option>
            ))}
          </select>
          <select
            value={hidden}
            onChange={(e) => { setHidden(e.target.value); resetPage(); }}
            className="border border-input rounded-lg px-3 py-2.5 sm:py-2 text-sm bg-card text-foreground min-w-0"
            aria-label="Filter by visibility"
          >
            <option value="">All + hidden</option>
            <option value="visible">Visible only</option>
            <option value="hidden">Hidden only</option>
          </select>
          <button
            type="button"
            onClick={() => setPhotosOnly((v) => !v)}
            aria-pressed={photosOnly}
            title="Show only reviews with customer photos"
            className={`border rounded-lg px-3 py-2.5 sm:py-2 text-sm flex items-center gap-1.5 transition min-w-0 whitespace-nowrap ${
              photosOnly
                ? 'border-primary bg-primary/10 text-foreground font-medium'
                : 'border-input bg-card text-foreground hover:bg-muted'
            }`}
          >
            <ImageIcon size={15} className={photosOnly ? 'text-primary' : 'text-muted-foreground'} aria-hidden="true" />
            With photos
          </button>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-border overflow-hidden">
        {/* Desktop: table */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full min-w-[820px]">
            <thead className="bg-muted border-b border-border">
              <tr>
                {['Rating', 'Review', 'Product', 'Author', 'Date', 'State', 'Actions'].map((head, i) => (
                  <th
                    key={head}
                    className={`text-left px-4 py-3 text-xs uppercase text-muted-foreground${i === 6 ? ' text-right' : ''}`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    {photosOnly && rows.length > 0
                      ? 'No reviews with photos on this page — clear the With photos filter to see all reviews.'
                      : 'No reviews match these filters.'}
                  </td>
                </tr>
              )}
              {visibleRows.map((review) => (
                <tr key={review.id} className={`hover:bg-muted/50 ${review.is_hidden ? 'opacity-60' : ''}`}>
                  <td className="px-4 py-3">
                    <Stars value={review.rating} />
                  </td>
                  <td className="px-4 py-3 max-w-[280px]">
                    {review.title && (
                      <p className="text-sm font-medium text-foreground truncate">{review.title}</p>
                    )}
                    {review.comment && (
                      <p className="text-xs text-muted-foreground truncate mt-0.5">{review.comment}</p>
                    )}
                    {review.is_verified_purchase && (
                      <p className="text-[11px] text-success mt-0.5">Verified purchase</p>
                    )}
                    <ReviewThumbs images={review.images || []} onOpen={(idx) => openLightbox(review, idx)} />
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground truncate max-w-[160px]">
                    {review.product_name || '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground truncate max-w-[180px]">
                    {review.user_full_name || review.user_email || '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                    {formatDate(review.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs ${review.is_hidden ? 'bg-muted text-muted-foreground' : 'bg-success/15 text-success'}`}>
                      {review.is_hidden ? 'Hidden' : 'Visible'}
                    </span>
                  </td>
                  <td className="px-4 py-3">{actionsFor(review)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile: stacked cards */}
        <div className="md:hidden divide-y divide-border">
          {visibleRows.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              {photosOnly && rows.length > 0
                ? 'No reviews with photos on this page — clear the With photos filter to see all reviews.'
                : 'No reviews match these filters.'}
            </p>
          )}
          {visibleRows.map((review) => (
            <div key={review.id} className={`p-4 space-y-2 ${review.is_hidden ? 'opacity-70' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <Stars value={review.rating} />
                <span className={`px-2 py-1 rounded-full text-xs shrink-0 ${review.is_hidden ? 'bg-muted text-muted-foreground' : 'bg-success/15 text-success'}`}>
                  {review.is_hidden ? 'Hidden' : 'Visible'}
                </span>
              </div>
              {review.title && (
                <p className="text-sm font-medium text-foreground">{review.title}</p>
              )}
              {review.comment && (
                <p className="text-sm text-muted-foreground">{review.comment}</p>
              )}
              <ReviewThumbs
                images={review.images || []}
                sizeClass="w-14 h-14"
                onOpen={(idx) => openLightbox(review, idx)}
              />
              <p className="text-xs text-muted-foreground">
                {review.product_name || '—'}
                {' · '}
                {review.user_full_name || review.user_email || '—'}
                {review.is_verified_purchase && ' · Verified purchase'}
              </p>
              <p className="text-xs text-muted-foreground">{formatDate(review.created_at)}</p>
              <div className="pt-1">{actionsFor(review, true)}</div>
            </div>
          ))}
        </div>

        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Showing {((page - 1) * ITEMS_PER_PAGE) + 1} -{' '}
              {Math.min(page * ITEMS_PER_PAGE, total)} of {total} reviews
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {lightbox && (
        <ImageLightbox
          key={`${lightbox.index}-${lightbox.images[lightbox.index]?.src}`}
          images={lightbox.images}
          initialIndex={lightbox.index}
          title={lightbox.title}
          onClose={() => setLightbox(null)}
        />
      )}

      <ConfirmDialog
        open={!!confirmState}
        busy={actingId != null}
        title={
          !confirmState
            ? ''
            : confirmState.kind === 'delete'
              ? 'Delete review'
              : !confirmState.target.is_hidden
                ? 'Hide review'
                : 'Unhide review'
        }
        message={
          !confirmState
            ? ''
            : confirmState.kind === 'delete'
              ? `Permanently delete this review of "${confirmState.target.product_name}"? This cannot be undone — prefer Hide unless it is pure spam.`
              : !confirmState.target.is_hidden
                ? `Hide this ${confirmState.target.rating}-star review of "${confirmState.target.product_name}"? It vanishes from the storefront instantly but stays on record.`
                : `Unhide this review of "${confirmState.target.product_name}"? It reappears on the storefront.`
        }
        confirmLabel={
          !confirmState
            ? 'Confirm'
            : confirmState.kind === 'delete'
              ? 'Delete'
              : !confirmState.target.is_hidden
                ? 'Hide'
                : 'Unhide'
        }
        tone={confirmState?.kind === 'delete' ? 'danger' : 'primary'}
        onConfirm={runConfirmed}
        onClose={() => { if (actingId == null) setConfirmState(null); }}
      />
    </div>
  );
};

export default Reviews;
