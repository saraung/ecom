import React, { useEffect, useState, useCallback, useRef } from 'react';

/**
 * ImageLightbox — Figma-style premium image popup.
 *
 * Pattern (Amazon / Flipkart / Figma community "Gallery Lightbox"):
 * - full-screen dark blurred backdrop, click to dismiss
 * - centered rounded card with the large image
 * - floating top bar: counter pill on the left, close button on the right
 * - side prev/next circular buttons (desktop), swipe on mobile
 * - bottom thumbnail strip with active ring
 * - keyboard: Esc closes, ←/→ navigate
 * - body scroll locked while open
 *
 * @param {Array<{src:string, alt?:string}>} images
 * @param {number} initialIndex
 * @param {() => void} onClose
 * @param {string} [title]  optional caption shown under the counter (e.g. reviewer name)
 */
const ImageLightbox = ({ images = [], initialIndex = 0, onClose, title = '' }) => {
  const [index, setIndex] = useState(initialIndex);
  const touchX = useRef(null);

  const hasMultiple = images.length > 1;

  const goTo = useCallback(
    (next) => {
      if (!images.length) return;
      setIndex((next + images.length) % images.length);
    },
    [images.length]
  );

  const goPrev = useCallback(() => goTo(index - 1), [goTo, index]);
  const goNext = useCallback(() => goTo(index + 1), [goTo, index]);

  // Note: the parent remounts this component (via `key`) for each new
  // popup, so `initialIndex` is consumed once at mount — no sync effect needed.

  // Keyboard navigation + scroll lock
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
      else if (e.key === 'ArrowLeft') goPrev();
      else if (e.key === 'ArrowRight') goNext();
    };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose, goPrev, goNext]);

  const onTouchStart = (e) => {
    touchX.current = e.touches[0].clientX;
  };
  const onTouchEnd = (e) => {
    if (touchX.current == null) return;
    const dx = e.changedTouches[0].clientX - touchX.current;
    if (Math.abs(dx) > 40) {
      if (dx > 0) goPrev();
      else goNext();
    }
    touchX.current = null;
  };

  if (!images.length) return null;
  const current = images[index];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title || `Image viewer, image ${index + 1} of ${images.length}`}
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 animate-fade-in"
    >
      {/* Backdrop — click to dismiss */}
      <div
        className="absolute inset-0 bg-black/75 backdrop-blur-md"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Card */}
      <div className="relative w-full max-w-3xl flex flex-col items-center animate-bounce-in">
        {/* Top bar: counter + title + close */}
        <div className="w-full flex items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            {hasMultiple && (
              <span className="shrink-0 bg-white/15 backdrop-blur-md text-white text-[11px] font-bold tracking-widest px-3 py-1.5 rounded-full border border-white/20">
                {index + 1} / {images.length}
              </span>
            )}
            {title && (
              <span className="truncate text-xs font-semibold text-white/80">{title}</span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close image viewer"
            autoFocus
            className="shrink-0 w-10 h-10 rounded-full bg-white/15 hover:bg-white/25 backdrop-blur-md border border-white/20 text-white flex items-center justify-center text-base transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Main image wrapper */}
        <div className="relative w-full flex items-center justify-center">
          {/* Prev (desktop) */}
          {hasMultiple && (
            <button
              type="button"
              onClick={goPrev}
              aria-label="Previous image"
              className="hidden sm:flex absolute -left-2 lg:-left-16 z-10 w-11 h-11 rounded-full bg-white text-black items-center justify-center text-lg font-bold shadow-xl hover:scale-110 active:scale-95 transition-transform"
            >
              ←
            </button>
          )}

          <div
            className="relative w-full max-h-[70vh] sm:max-h-[75vh] rounded-[1.5rem] overflow-hidden bg-black/40 border border-white/15 shadow-2xl flex items-center justify-center"
            onTouchStart={onTouchStart}
            onTouchEnd={onTouchEnd}
          >
            <img
              key={current.src}
              src={current.src}
              alt={current.alt || `Image ${index + 1}`}
              className="w-full h-full max-h-[70vh] sm:max-h-[75vh] object-contain animate-fade-in"
              draggable={false}
            />
          </div>

          {/* Next (desktop) */}
          {hasMultiple && (
            <button
              type="button"
              onClick={goNext}
              aria-label="Next image"
              className="hidden sm:flex absolute -right-2 lg:-right-16 z-10 w-11 h-11 rounded-full bg-white text-black items-center justify-center text-lg font-bold shadow-xl hover:scale-110 active:scale-95 transition-transform"
            >
              →
            </button>
          )}
        </div>

        {/* Mobile prev/next */}
        {hasMultiple && (
          <div className="flex sm:hidden items-center gap-3 mt-4">
            <button
              type="button"
              onClick={goPrev}
              aria-label="Previous image"
              className="w-11 h-11 rounded-full bg-white/15 backdrop-blur-md border border-white/20 text-white flex items-center justify-center text-lg"
            >
              ←
            </button>
            <span className="text-white/70 text-xs font-bold tracking-widest">
              {index + 1} / {images.length}
            </span>
            <button
              type="button"
              onClick={goNext}
              aria-label="Next image"
              className="w-11 h-11 rounded-full bg-white/15 backdrop-blur-md border border-white/20 text-white flex items-center justify-center text-lg"
            >
              →
            </button>
          </div>
        )}

        {/* Thumbnails */}
        {hasMultiple && (
          <div className="hidden sm:flex gap-2 mt-4 max-w-full overflow-x-auto pb-1 scrollbar-hide">
            {images.map((img, i) => (
              <button
                key={`${img.src}-${i}`}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`View image ${i + 1}`}
                aria-current={i === index}
                className={`relative w-14 h-14 flex-shrink-0 rounded-xl overflow-hidden transition-all duration-200 ${
                  i === index
                    ? 'ring-2 ring-white scale-100 opacity-100'
                    : 'opacity-50 hover:opacity-100 scale-95'
                }`}
              >
                <img
                  src={img.src}
                  alt=""
                  loading="lazy"
                  className="w-full h-full object-cover"
                  draggable={false}
                />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ImageLightbox;
