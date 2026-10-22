import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ImagePlus, X } from 'lucide-react';
import api from '../../api/axios';
import { reviewAPI } from '../../api/review';
import { useCart } from '../../hooks/useCart';
import { useAuth } from '../../hooks/useAuth';
import { useModalA11y } from '../../hooks/useModalA11y';
import { ProductDetailSkeleton } from '../../components/common/Skeleton';
import ImageLightbox from '../../components/common/ImageLightbox';
import { formatPrice } from '../../utils/format';

const ProductDetail = () => {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { isAuthenticated, user } = useAuth();
  const queryClient = useQueryClient();

  // Product detail is cached per slug. A 404 is a permanent answer, so it is
  // not retried; the error message is derived from the HTTP status.
  const {
    data: product = null,
    isPending: loading,
    error: productQueryError,
  } = useQuery({
    queryKey: ['product', slug],
    queryFn: ({ signal }) => api.get(`/products/${slug}`, { signal }).then((res) => res.data),
    enabled: !!slug,
    retry: (failureCount, err) => err?.response?.status !== 404 && failureCount < 1,
  });

  const error = productQueryError
    ? productQueryError.response?.status === 404
      ? 'Product not found'
      : 'Failed to load product details'
    : '';
  
  const [quantity, setQuantity] = useState(1);
  const [selectedVariant, setSelectedVariant] = useState(null);
  const [selectedImage, setSelectedImage] = useState(0);
  const [showSuccess, setShowSuccess] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  // Lightbox popup: { images: [{src, alt}], index, title } | null
  const [lightbox, setLightbox] = useState(null);

  // Escape closes, focus trapped/restored, scroll locked while the sign-in prompt is open.
  const loginDialogRef = useModalA11y(() => setShowLoginModal(false), showLoginModal);

  // Reviews state
  const {
    data: reviews = [],
    isPending: reviewsLoading,
  } = useQuery({
    queryKey: ['reviews', product?.id],
    queryFn: () => reviewAPI.getProductReviews(product.id).then((res) => res.data),
    enabled: !!product?.id,
  });
  const setReviews = (updater) =>
    queryClient.setQueryData(['reviews', product?.id], (prev = []) =>
      typeof updater === 'function' ? updater(prev) : updater
    );
  const [reviewForm, setReviewForm] = useState({ rating: 5, title: '', comment: '' });
  const [reviewFiles, setReviewFiles] = useState([]);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewError, setReviewError] = useState('');
  const [reviewSuccess, setReviewSuccess] = useState(false);
  // Local preview URLs for selected review photos (revoked on change/unmount)
  const [reviewPreviews, setReviewPreviews] = useState([]);

  useEffect(() => {
    if (!reviewFiles.length) {
      setReviewPreviews([]);
      return;
    }
    const urls = reviewFiles.map((file) => URL.createObjectURL(file));
    setReviewPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [reviewFiles]);

  const handleReviewFilesChange = (event) => {
    const picked = Array.from(event.target.files || []);
    event.target.value = '';
    if (!picked.length) return;
    const next = [...reviewFiles, ...picked];
    if (next.length > 6 || next.some((file) => file.size > 5 * 1024 * 1024)) {
      setReviewError('Choose up to 6 images, 5 MB each.');
      return;
    }
    setReviewError('');
    setReviewFiles(next);
  };

  const removeReviewFile = (idx) => {
    setReviewFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  // Default to the first variant whenever a different product arrives. A
  // background refetch of the same product keeps the shopper's selection.
  useEffect(() => {
    if (product?.variants?.length) {
      setSelectedVariant((current) =>
        current && product.variants.some((variant) => variant.id === current.id)
          ? current
          : product.variants[0]
      );
    }
  }, [product]);

  const handleReviewSubmit = async (e) => {
    e.preventDefault();
    if (!product) return;

    setReviewSubmitting(true);
    setReviewError('');

    try {
      const res = await reviewAPI.createReviewWithImages(product.id, reviewForm, reviewFiles);
      setReviews((prev) => [res.data, ...prev]);
      setReviewForm({ rating: 5, title: '', comment: '' });
      setReviewFiles([]);
      setReviewSuccess(true);
      setTimeout(() => setReviewSuccess(false), 3000);
    } catch (err) {
      setReviewError(err.response?.data?.detail || 'Failed to submit review.');
    } finally {
      setReviewSubmitting(false);
    }
  };

  const handleReviewDelete = async (reviewId) => {
    if (!window.confirm('Are you sure you want to delete this review?')) return;
    try {
      await reviewAPI.deleteReview(reviewId);
      setReviews((prev) => prev.filter((r) => r.id !== reviewId));
    } catch (err) {
      setReviewError(err.response?.data?.detail || 'Failed to delete review.');
    }
  };

  const handleAddToCart = async () => {
    if (!isAuthenticated) return setShowLoginModal(true);
    if (!product || !product.variants?.length) return alert('Not available for purchase.');

    let variantToUse = selectedVariant || product.variants[0];
    if (!variantToUse?.id) return alert('Select a variant first.');
    if ((variantToUse.stock ?? 0) <= 0) return alert('Out of stock.');

    const result = await addToCart({
      id: product.id,
      name: product.name,
      price: parseFloat(variantToUse?.effective_price || product.price),
      slug: product.slug,
      quantity,
      variant: variantToUse,
      variant_id: variantToUse.id,
      image: product.images?.[0]?.url || null
    });

    if (result.success) {
      setShowSuccess(true);
      setTimeout(() => setShowSuccess(false), 3000);
    } else {
      alert(result.message || 'Failed to add to cart.');
    }
  };

  if (loading) {
    return <ProductDetailSkeleton />;
  }

  if (error || !product) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background transition-colors duration-700">
        <div className="text-center p-8 bg-card rounded-[2rem] shadow-[0_20px_50px_rgba(0,0,0,0.05)] dark:shadow-[0_20px_50px_rgba(0,0,0,0.4)] border border-border max-w-sm mx-4">
          <div className="text-5xl mb-4">🔍</div>
          <h2 className="text-xl font-bold text-foreground mb-2">{error || 'Product not found'}</h2>
          <p className="text-sm text-muted-foreground mb-6">This piece might have been removed or doesn't exist.</p>
          <Link to="/products" className="bg-primary text-primary-foreground px-6 py-3 rounded-full font-bold uppercase tracking-wide text-sm hover:scale-105 transition-transform duration-300 inline-block shadow-xl">
            Return to Catalog
          </Link>
        </div>
      </div>
    );
  }

  const currentPrice = parseFloat(selectedVariant?.effective_price || product.price);
  const currentComparePrice = parseFloat(product.compare_at_price || 0);
  const savings = currentComparePrice > currentPrice ? currentComparePrice - currentPrice : 0;
  const imageUrl = product.images?.[selectedImage]?.url || product.images?.[0]?.url;
  const hasVariants = product.variants?.length > 0;
  const currentStock = selectedVariant?.stock ?? 0;
  const isSelectedOutOfStock = currentStock <= 0;
  const avgRating = Number(product.average_rating) || 0;

  return (
    <div className="bg-background min-h-screen selection:bg-primary selection:text-primary-foreground transition-colors duration-700 pb-20">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8">
        
        {/* Breadcrumb */}
        <nav className="flex gap-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-8">
          <Link to="/" className="hover:text-foreground transition-colors">Home</Link>
          <span>/</span>
          <Link to="/products" className="hover:text-foreground transition-colors">Products</Link>
          <span>/</span>
          <span className="text-foreground truncate max-w-[150px]">{product.name}</span>
        </nav>

        <div className="flex flex-col lg:flex-row gap-10 lg:gap-12 items-start">
          
          {/* Left Column – Images (Sticky). `min-w-0` keeps long unbroken
              strings (URLs, SKU codes) from stretching the flex column
              past the viewport on narrow mobile widths. */}
          <div className="w-full min-w-0 lg:w-1/2 lg:sticky lg:top-24 flex flex-col gap-4">
            <div className="relative group w-full aspect-square rounded-[1.5rem] sm:rounded-[2rem] bg-primary-soft overflow-hidden shadow-[0_10px_30px_rgba(0,0,0,0.05)] dark:shadow-[0_10px_30px_rgba(0,0,0,0.4)] border border-border/50">
              {imageUrl ? (
                <button
                  type="button"
                  onClick={() => setLightbox({
                    images: (product.images || []).map((img, i) => ({
                      src: img.url,
                      alt: `${product.name} — view ${i + 1}`
                    })),
                    index: selectedImage,
                    title: product.name
                  })}
                  aria-label={`Open image viewer for ${product.name}`}
                  className="block w-full h-full cursor-zoom-in focus:outline-none"
                >
                  <img
                    src={imageUrl}
                    alt={product.name}
                    className="w-full h-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                  />
                </button>
              ) : (
                <div className="w-full h-full flex items-center justify-center text-muted-foreground font-medium text-sm">No Image Available</div>
              )}

              {/* Expand hint — appears on hover / always visible on touch */}
              {imageUrl && (
                <span className="absolute bottom-4 right-4 pointer-events-none w-10 h-10 rounded-full bg-card/90 backdrop-blur-md border border-border/80 flex items-center justify-center text-foreground text-base shadow-lg opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity" aria-hidden="true">
                  ⤢
                </span>
              )}

              {/* Floating Badges */}
              <div className="absolute top-4 left-4 flex flex-col gap-2">
                {product.discount_percentage > 0 && (
                  <span className="bg-primary/90 backdrop-blur-md text-primary-foreground px-3 py-1.5 rounded-full text-[10px] font-bold tracking-widest uppercase shadow-md">
                    {product.discount_percentage}% Off
                  </span>
                )}
                {product.is_on_sale && (
                  <span className="bg-success/90 backdrop-blur-md text-primary-foreground px-3 py-1.5 rounded-full text-[10px] font-bold tracking-widest uppercase shadow-md">
                    Sale
                  </span>
                )}
              </div>
            </div>

            {/* Thumbnails — the frame is an INSET border (not ring-offset shadow):
                `ring-offset` paints outside the 64px button, and this row is
                `overflow-x-auto` (which also clips vertically), so the selected
                thumb's ring was cut off / visually overflowing the small frame.
                Border keeps the frame neatly inside its own box on all screens. */}
            {product.images?.length > 1 && (
              <div className="flex gap-3 overflow-x-auto pb-1 snap-x scrollbar-hide">
                {product.images.map((image, idx) => (
                  <button
                    key={image.id}
                    type="button"
                    onClick={() => setSelectedImage(idx)}
                    aria-label={`View image ${idx + 1} of ${product.images.length}`}
                    aria-current={selectedImage === idx}
                    className={`relative w-16 h-16 flex-shrink-0 rounded-xl overflow-hidden snap-center transition-all duration-300 ease-out
                      ${selectedImage === idx
                        ? 'border-2 border-primary scale-100'
                        : 'border-2 border-transparent opacity-60 hover:opacity-100 scale-95'}`}
                  >
                    <img
                      src={image.url}
                      alt={`Product view ${idx + 1}`}
                      loading="lazy"
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Right Column – Product Details */}
          <div className="w-full min-w-0 lg:w-1/2 flex flex-col gap-8 pb-10">
            
            {/* Header */}
            <div>
              <h1 className="text-3xl md:text-4xl lg:text-5xl font-extrabold tracking-tighter text-foreground leading-[1.1]">
                {product.name}
              </h1>
              
              <div className="flex items-center gap-3 mt-4">
                <div className="flex text-foreground dark:text-warning text-sm">
                  {[...Array(5)].map((_, i) => (
                    <span key={i}>{i < Math.round(avgRating) ? '★' : '☆'}</span>
                  ))}
                </div>
                <span className="text-sm text-muted-foreground font-medium underline decoration-border underline-offset-4 cursor-pointer hover:text-foreground transition-colors">
                  {product.review_count} Reviews
                </span>
              </div>
            </div>

            {/* Price Block */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-end gap-3 flex-wrap">
                <span className="text-3xl md:text-4xl font-bold text-foreground tracking-tight">
                  {formatPrice(currentPrice)}
                </span>
                {savings > 0 && (
                  <span className="text-lg text-muted-foreground line-through decoration-border font-medium mb-1">
                    {formatPrice(currentComparePrice)}
                  </span>
                )}
              </div>
              {savings > 0 && (
                <span className="inline-flex items-center gap-1 bg-success-soft text-success-soft-foreground px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider">
                  You save {formatPrice(savings)}
                </span>
              )}
            </div>

            {/* Description */}
            <p className="text-base text-muted-foreground leading-relaxed font-medium">
              {product.description || 'Premium quality, uncompromised design.'}
            </p>

            <hr className="border-border" />

            {/* Variants */}
            {hasVariants ? (
              <div className="flex flex-col gap-3">
                <h3 className="text-xs font-bold uppercase tracking-widest text-foreground">Configuration</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {product.variants.map((variant) => {
                    const isSelected = selectedVariant?.id === variant.id;
                    const isOutOfStock = (variant.stock ?? 0) <= 0;
                    return (
                      <button
                        key={variant.id}
                        onClick={() => { setSelectedVariant(variant); setQuantity(1); }}
                        className={`relative p-4 rounded-2xl border-2 text-left transition-all duration-300 ease-out
                          ${isSelected 
                            ? 'border-primary bg-primary-soft shadow-sm scale-[1.02]' 
                            : 'border-border bg-transparent hover:border-border hover:bg-primary-soft/50'}
                          ${isOutOfStock ? 'opacity-50 grayscale cursor-not-allowed' : ''}`}
                      >
                        <div className={`font-bold text-base ${isSelected ? 'text-foreground' : 'text-foreground/80'}`}>
                          {variant.sku}
                        </div>
                        {variant.attributes && (
                          <div className="text-[10px] font-medium text-muted-foreground mt-1 uppercase tracking-wider">
                            {Object.entries(variant.attributes).map(([k, v]) => `${v}`).join(' · ')}
                          </div>
                        )}
                        {isOutOfStock ? (
                          <span className="absolute top-3 right-3 text-[9px] bg-destructive-soft text-destructive px-2 py-0.5 rounded font-bold uppercase">Sold out</span>
                        ) : variant.stock <= 3 && (
                          <span className="absolute top-3 right-3 text-[9px] bg-warning-soft text-warning px-2 py-0.5 rounded font-bold uppercase">Only {variant.stock} left</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-2xl bg-primary-soft border border-border">
                <p className="text-sm text-muted-foreground font-medium">Currently unavailable for purchase.</p>
              </div>
            )}

            {/* Actions (Quantity + Add to Cart) */}
            <div className="flex flex-col gap-4 mt-2">
              <div className="flex items-center gap-4">
                <h3 className="text-xs font-bold uppercase tracking-widest text-foreground w-20">Quantity</h3>
                <div className={`flex items-center bg-card border-2 border-border rounded-full h-12 ${isSelectedOutOfStock ? 'opacity-50' : ''}`}>
                  <button
                    onClick={() => setQuantity(Math.max(1, quantity - 1))}
                    disabled={quantity <= 1 || isSelectedOutOfStock}
                    className="w-12 h-full flex items-center justify-center text-lg text-muted-foreground hover:text-foreground transition-colors disabled:hover:text-muted-foreground"
                  >−</button>
                  <span className="w-10 text-center font-bold text-sm text-foreground">{isSelectedOutOfStock ? 0 : quantity}</span>
                  <button
                    onClick={() => setQuantity(Math.min(currentStock, quantity + 1))}
                    disabled={quantity >= currentStock || isSelectedOutOfStock}
                    className="w-12 h-full flex items-center justify-center text-lg text-muted-foreground hover:text-foreground transition-colors disabled:hover:text-muted-foreground"
                  >+</button>
                </div>
              </div>

              <button
                onClick={handleAddToCart}
                disabled={!product.is_active || isSelectedOutOfStock}
                className={`w-full py-4 rounded-full font-bold text-sm tracking-widest uppercase transition-all duration-300 ease-out shadow-lg
                  ${isSelectedOutOfStock || !product.is_active
                    ? 'bg-primary-soft text-muted-foreground cursor-not-allowed shadow-none'
                    : 'bg-primary text-primary-foreground hover:bg-primary-hover hover:-translate-y-0.5 hover:shadow-[0_15px_30px_rgba(0,0,0,0.2)] dark:hover:shadow-[0_15px_30px_rgba(255,255,255,0.15)]'
                  }`}
              >
                {isSelectedOutOfStock ? 'Out of Stock' : !isAuthenticated ? 'Login to Purchase' : 'Add to Bag'}
              </button>
            </div>

            {/* Trust Badges — honest: no returns flow exists, so no returns promise. */}
            <div className="grid grid-cols-3 gap-3 pt-6 border-t border-border mt-2">
              {[
                { icon: '📦', title: 'Free Shipping', sub: `Over ${formatPrice(500)}` },
                { icon: '💵', title: 'COD Available', sub: 'Pay on delivery' },
                { icon: '🛡️', title: 'Secure Check', sub: '256-bit encryption' }
              ].map((badge, i) => (
                <div key={i} className="flex flex-col items-center text-center p-3 rounded-2xl bg-card shadow-[0_2px_10px_rgba(0,0,0,0.02)] dark:shadow-none border border-border">
                  <span className="text-2xl mb-2 dark:opacity-80">{badge.icon}</span>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-foreground mb-0.5">{badge.title}</span>
                  <span className="text-[9px] text-muted-foreground font-medium">{badge.sub}</span>
                </div>
              ))}
            </div>

          </div>
        </div>

        {/* Reviews Section */}
        <div className="mt-20 max-w-3xl mx-auto">
          <h2 className="text-2xl font-extrabold tracking-tight text-foreground mb-8 text-center">Community Voices</h2>

          {isAuthenticated ? (
            <form onSubmit={handleReviewSubmit} className="bg-card p-6 rounded-[1.5rem] shadow-[0_5px_20px_rgba(0,0,0,0.04)] dark:shadow-[0_5px_20px_rgba(0,0,0,0.4)] mb-12 border border-border">
              <h3 className="text-xs font-bold uppercase tracking-widest text-foreground mb-6">Share your experience</h3>
              
              <div className="flex gap-1 mb-6">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    type="button"
                    key={star}
                    onClick={() => setReviewForm(f => ({ ...f, rating: star }))}
                    className={`text-2xl transition-transform hover:scale-110 ${star <= reviewForm.rating ? 'text-foreground dark:text-warning' : 'text-border'}`}
                  >
                    ★
                  </button>
                ))}
              </div>

              <div className="space-y-4">
                <input
                  type="text"
                  placeholder="Review Title"
                  value={reviewForm.title}
                  onChange={(e) => setReviewForm(f => ({ ...f, title: e.target.value }))}
                  className="w-full bg-primary-soft border-none rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground"
                />
                <textarea
                  placeholder="Tell us more about this piece..."
                  value={reviewForm.comment}
                  onChange={(e) => setReviewForm(f => ({ ...f, comment: e.target.value }))}
                  rows={3}
                  className="w-full bg-primary-soft border-none rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground resize-none"
                />
                {/* Photo uploader — thumbnail tiles + add tile (not a text field) */}
                <div>
                  <div className="flex items-center justify-between mb-2 px-1">
                    <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                      Photos <span className="normal-case font-medium">(optional)</span>
                    </span>
                    <span className="text-[11px] font-bold text-muted-foreground tabular-nums">
                      {reviewFiles.length}/6
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {reviewPreviews.map((preview, idx) => (
                      <div
                        key={`${reviewFiles[idx]?.name}-${idx}`}
                        className="relative h-20 w-20 rounded-xl overflow-hidden border border-border bg-primary-soft group/preview"
                      >
                        <img
                          src={preview}
                          alt={`Selected photo ${idx + 1}`}
                          className="h-full w-full object-cover"
                        />
                        <button
                          type="button"
                          onClick={() => removeReviewFile(idx)}
                          aria-label={`Remove photo ${idx + 1}`}
                          className="absolute top-1 right-1 w-6 h-6 min-h-0 min-w-0 rounded-full bg-black/60 hover:bg-black/80 backdrop-blur-sm text-white flex items-center justify-center transition-colors"
                        >
                          <X size={12} strokeWidth={3} />
                        </button>
                      </div>
                    ))}
                    {reviewFiles.length < 6 && (
                      <label
                        className="h-20 w-20 rounded-xl border-2 border-dashed border-border hover:border-primary bg-transparent hover:bg-primary-soft/50 flex flex-col items-center justify-center gap-1 cursor-pointer text-muted-foreground hover:text-foreground transition-colors"
                        title="Add photos"
                      >
                        <ImagePlus size={22} strokeWidth={1.8} aria-hidden="true" />
                        <span className="text-[10px] font-bold uppercase tracking-wider">Add</span>
                        <input
                          type="file"
                          multiple
                          accept="image/jpeg,image/png,image/webp"
                          className="sr-only"
                          disabled={reviewSubmitting}
                          onChange={handleReviewFilesChange}
                        />
                      </label>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground font-medium mt-2 px-1">
                    JPG, PNG or WebP, up to 5 MB each.
                  </p>
                </div>
                {reviewError && <p className="text-destructive font-medium text-xs px-2">{reviewError}</p>}
                
                <button
                  type="submit"
                  disabled={reviewSubmitting}
                  className="bg-primary text-primary-foreground px-6 py-3 rounded-full font-bold uppercase tracking-widest text-xs hover:scale-105 transition-all duration-300 disabled:opacity-50 shadow-md"
                >
                  {reviewSubmitting ? 'Publishing...' : 'Publish Review'}
                </button>
              </div>
            </form>
          ) : (
            <div className="text-center mb-12">
              <p className="text-sm text-muted-foreground font-medium">
                <button onClick={() => setShowLoginModal(true)} className="text-foreground font-bold underline underline-offset-4">Sign in</button> to share your thoughts.
              </p>
            </div>
          )}

          <div className="space-y-4">
            {reviewsLoading ? (
              <p className="text-center text-sm text-muted-foreground font-medium animate-pulse">Loading community reviews...</p>
            ) : reviews.length === 0 ? (
              <p className="text-center text-sm text-muted-foreground font-medium">Be the first to review this piece.</p>
            ) : (
              reviews.map((review) => (
                <div key={review.id} className="bg-card p-6 rounded-[1.5rem] border border-border shadow-sm hover:shadow-[0_5px_15px_rgba(0,0,0,0.03)] dark:hover:shadow-[0_5px_15px_rgba(0,0,0,0.4)] transition-shadow duration-300">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="text-foreground dark:text-warning text-sm">
                        {[...Array(5)].map((_, i) => <span key={i}>{i < review.rating ? '★' : '☆'}</span>)}
                      </div>
                      <span className="font-bold text-sm text-foreground">{review.user_full_name || 'Anonymous'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {review.is_verified_purchase && (
                        <span className="bg-success-soft text-success px-2 py-1 rounded-md text-[9px] font-bold uppercase tracking-wider">
                          Verified
                        </span>
                      )}
                      {user && review.user_id === user.id && (
                        <button
                          type="button"
                          onClick={() => handleReviewDelete(review.id)}
                          className="text-muted-foreground hover:text-destructive transition-colors text-xs font-semibold px-2 py-1 rounded-md hover:bg-destructive/10"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                   {review.title && <h4 className="text-base font-bold text-foreground mb-1">{review.title}</h4>}
                   {review.comment && <p className="text-sm text-muted-foreground leading-relaxed font-medium mb-3">{review.comment}</p>}
                   {review.images?.length > 0 && (
                     <div className="flex flex-wrap gap-2 mb-3">
                       {review.images.map((image, imgIdx) => (
                         <button
                           key={image.id}
                           type="button"
                           onClick={() => setLightbox({
                             images: review.images.map((img, i) => ({
                               src: img.secure_url,
                               alt: `Review by ${review.user_full_name || 'customer'} — photo ${i + 1}`
                             })),
                             index: imgIdx,
                             title: `Review by ${review.user_full_name || 'Anonymous'}`
                           })}
                           aria-label={`Open review photo ${imgIdx + 1} of ${review.images.length}`}
                           className="group/review-img relative h-20 w-20 rounded-xl overflow-hidden border border-border cursor-zoom-in hover:border-primary hover:scale-105 active:scale-95 transition-all duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                         >
                           <img
                             src={image.secure_url}
                             alt={`Customer review photo ${imgIdx + 1}`}
                             loading="lazy"
                             className="h-full w-full object-cover"
                           />
                           <span className="absolute inset-0 bg-black/0 group-hover/review-img:bg-black/20 transition-colors flex items-center justify-center text-white text-lg opacity-0 group-hover/review-img:opacity-100" aria-hidden="true">
                             ⤢
                           </span>
                         </button>
                       ))}
                     </div>
                   )}
                  <p className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">
                    {new Date(review.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Floating Success Toast */}
      <div className={`fixed bottom-8 left-1/2 -translate-x-1/2 z-50 transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)] ${showSuccess ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-10 opacity-0 scale-95 pointer-events-none'}`}>
        <div className="bg-primary/95 backdrop-blur-md text-primary-foreground px-6 py-3 rounded-full shadow-2xl flex items-center gap-3 border border-border">
          <div className="w-5 h-5 rounded-full bg-card text-foreground flex items-center justify-center text-[10px] font-bold">✓</div>
          <span className="text-sm font-bold tracking-wide">Added to your bag</span>
        </div>
      </div>

      {/* Review Success Toast */}
      <div className={`fixed bottom-8 left-1/2 -translate-x-1/2 z-50 transition-all duration-500 ease-out ${reviewSuccess ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-10 opacity-0 scale-95 pointer-events-none'}`}>
        <div className="bg-primary/95 backdrop-blur-md text-primary-foreground px-6 py-3 rounded-full shadow-2xl flex items-center gap-3">
          <span className="text-sm font-bold tracking-wide">Review published</span>
        </div>
      </div>

      {/* Premium Login Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-foreground/40 backdrop-blur-xl transition-opacity" onClick={() => setShowLoginModal(false)} />
          <div
            ref={loginDialogRef}
            role="dialog"
            aria-modal="true"
            aria-label="Sign in required"
            className="relative bg-card w-full max-w-sm p-6 sm:p-8 rounded-[2rem] shadow-[0_20px_70px_rgba(0,0,0,0.2)] transform scale-100 animate-[popUp_0.3s_ease-out] border border-border"
          >
            <button 
              type="button"
              onClick={() => setShowLoginModal(false)}
              className="absolute top-4 right-4 w-8 h-8 bg-primary-soft rounded-full flex items-center justify-center text-muted-foreground hover:bg-primary-soft hover:text-foreground transition-colors"
              aria-label="Close"
            >
              ✕
            </button>
            <div className="text-center mt-2">
              <div className="w-16 h-16 bg-primary-soft rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-3xl">🔒</span>
              </div>
              <h3 className="text-xl font-extrabold tracking-tight text-foreground mb-2">Sign in required</h3>
              <p className="text-sm text-muted-foreground font-medium mb-6">Access your account to save items to your bag and speed up checkout.</p>
              
              <div className="space-y-3">
                <button
                  type="button"
                  onClick={() => { setShowLoginModal(false); navigate('/login', { state: { from: `/products/${slug}` } }); }}
                  className="w-full bg-primary text-primary-foreground py-3.5 rounded-full font-bold uppercase tracking-widest text-xs hover:scale-105 transition-all shadow-lg"
                >
                  Continue to Sign In
                </button>
                <button
                  type="button"
                  onClick={() => setShowLoginModal(false)}
                  className="w-full bg-transparent text-muted-foreground py-3 rounded-full font-bold uppercase tracking-widest text-xs hover:text-foreground transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Image Lightbox popup — product gallery + review photos */}
      {lightbox && (
        <ImageLightbox
          key={`${lightbox.index}-${lightbox.images[lightbox.index]?.src}`}
          images={lightbox.images}
          initialIndex={lightbox.index}
          title={lightbox.title}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
};

export default ProductDetail;
