import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ChevronLeft, ChevronRight } from 'lucide-react';
import heroAsset from '../../assets/hero.png';
import ProductCard from '../../components/common/ProductCard';
import { ProductGridSkeleton } from '../../components/common/Skeleton';
import api from '../../api/axios';
import { getContentBlocks } from '../../api/content';

// The chat widget pulls in react-markdown; load it only when Home renders it
// instead of inflating the initial bundle.
const Chatbot = lazy(() => import('../../components/common/Chatbot'));

// Hardcoded fallback — the hero renders exactly this when no live
// `home.hero` block exists, so the page can never look broken.
const FALLBACK_HERO = {
  titleTop: 'Define your',
  titleGradient: 'standard.',
  body: 'Engineered for excellence. A curated selection of premium pieces designed to elevate your everyday experience. No compromises.',
  ctaLabel: 'Shop Collection',
  ctaLink: '/products',
};

const EDITORIAL_CARDS = [
  { eyebrow: '01 / The everyday', title: 'Quiet essentials', index: 0 },
  { eyebrow: '02 / The statement', title: 'A little extra', index: 1 },
  { eyebrow: '03 / The considered', title: 'Made to last', index: 2 },
];

const getProductImage = (product) => product?.images?.[0]?.url || '';

const getHeroHref = (slide) => {
  const href = (slide.link || '').trim() || FALLBACK_HERO.ctaLink;
  return (href.startsWith('/') && !href.startsWith('//')) || /^https?:\/\//i.test(href)
    ? href
    : FALLBACK_HERO.ctaLink;
};

const HeroLink = ({ slide, className, children, ...props }) => {
  const href = getHeroHref(slide);
  if (/^https?:\/\//i.test(href)) {
    return <a href={href} target="_blank" rel="noreferrer" className={className} {...props}>{children}</a>;
  }
  return <Link to={href} className={className} {...props}>{children}</Link>;
};

const HeroCopy = ({ slide, heading = 'h2', className = '', inverted = false, compact = false }) => {
  const Heading = heading;
  return (
    <div className={className}>
      <p className={`${compact ? 'mb-2 text-[9px] md:mb-4 md:text-[10px]' : 'mb-4 text-[10px]'} font-bold uppercase tracking-[0.22em] ${inverted ? 'text-white/80' : 'text-accent'}`}>A considered collection</p>
      <Heading className={`text-balance ${compact ? 'line-clamp-3 text-2xl md:line-clamp-none md:text-4xl lg:text-6xl' : 'text-4xl sm:text-5xl lg:text-6xl'} font-extrabold leading-[0.98] tracking-[-0.055em] ${inverted ? 'text-white' : 'text-foreground'}`}>
        {slide.title}
      </Heading>
      {slide.body && <p className={`${compact ? 'mt-2 line-clamp-2 text-xs md:mt-4 md:line-clamp-none md:text-sm lg:text-base' : 'mt-4 text-sm sm:text-base'} max-w-lg leading-relaxed ${inverted ? 'text-white/90' : 'text-muted-foreground'}`}>{slide.body}</p>}
      {slide.layout_mode !== 'artwork' && (
        <HeroLink slide={slide} className={`${compact ? 'mt-3 px-5 py-2 text-[10px] md:mt-7 md:px-7 md:py-3.5 md:text-xs lg:text-sm' : 'mt-7 px-7 py-3.5 text-xs sm:text-sm'} inline-flex w-fit items-center justify-center rounded-full bg-primary font-bold tracking-widest uppercase text-primary-foreground transition-all duration-300 hover:-translate-y-0.5 hover:bg-primary-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}>
          {(slide.link_label || '').trim() || FALLBACK_HERO.ctaLabel}
        </HeroLink>
      )}
    </div>
  );
};

const imagePosition = (value) => ({
  center: 'center',
  top: 'center top',
  bottom: 'center bottom',
  left: 'left center',
  right: 'right center',
}[value] || 'center');

const HeroPhoto = ({ slide, ready, className = '', alt = '', fit = 'cover' }) => (
  <picture className={`block ${className}`}>
    {slide.mobile_image_url && slide.mobile_image_url !== slide.image_url && (
      <source media="(max-width: 767px)" srcSet={slide.mobile_image_url} />
    )}
    {ready && (
      <img
        src={slide.image_url}
        alt={alt}
        className={`absolute inset-0 h-full w-full ${fit === 'contain' ? 'object-contain' : 'object-cover'}`}
        style={{ objectPosition: imagePosition(slide.image_position) }}
      />
    )}
  </picture>
);

const Home = () => {
  // Featured products and hero slides are served from the query cache, so
  // returning to Home does not re-download the catalog or re-flash skeletons.
  const {
    data: featuredProducts = [],
    isPending: loading,
    isError: productError,
    refetch: retryProducts,
  } = useQuery({
    queryKey: ['products', 'featured'],
    queryFn: ({ signal }) =>
      api
        .get('/products/', { params: { limit: 8, sort: 'newest' }, signal })
        .then((response) => response.data.slice(0, 8)),
  });

  const { data: slides = [] } = useQuery({
    queryKey: ['content', 'home.hero'],
    queryFn: () => getContentBlocks(['home.hero']).then((blocks) => blocks['home.hero'] || []),
  });

  const [index, setIndex] = useState(0);
  const [isDesktop, setIsDesktop] = useState(false);
  const [touchStartX, setTouchStartX] = useState(null);
  const [isHovered, setIsHovered] = useState(false);
  const [hasFocusWithin, setHasFocusWithin] = useState(false);
  const [pageVisible, setPageVisible] = useState(
    () => typeof document !== 'undefined' && document.visibilityState === 'visible'
  );
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
  // Slide ids whose cover image actually loads (page URLs etc. stay text-only).
  const [imgOk, setImgOk] = useState({});

  useEffect(() => {
    setIndex(0);
  }, [slides.length]);

  useEffect(() => {
    const query = window.matchMedia('(min-width: 768px)');
    setIsDesktop(query.matches);
    const onChange = (e) => setIsDesktop(e.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onMotionChange = (event) => setPrefersReducedMotion(event.matches);
    const onVisibilityChange = () => setPageVisible(document.visibilityState === 'visible');
    motionQuery.addEventListener('change', onMotionChange);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      motionQuery.removeEventListener('change', onMotionChange);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  // Preload both art-directed crops; failed images stay out of the layout.
  useEffect(() => {
    let cancelled = false;
    setImgOk({});
    slides.forEach((slide) => {
      [slide.image_url, slide.mobile_image_url]
        .map((src) => (src || '').trim())
        .filter((src, index, all) => src && all.indexOf(src) === index)
        .forEach((src) => {
          const img = new Image();
          img.onload = () => {
            if (!cancelled) setImgOk((prev) => ({ ...prev, [`${slide.id}:${src}`]: true }));
          };
          img.src = src;
        });
    });
    return () => {
      cancelled = true;
    };
  }, [slides]);

  const goTo = (i) => {
    if (!slides.length) return;
    setIndex(((i % slides.length) + slides.length) % slides.length);
  };

  useEffect(() => {
    if (slides.length < 2 || isHovered || hasFocusWithin || !pageVisible || prefersReducedMotion) return undefined;
    const timer = window.setTimeout(() => {
      setIndex((current) => (current + 1) % slides.length);
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [slides.length, index, isHovered, hasFocusWithin, pageVisible, prefersReducedMotion]);

  return (
    <div className="bg-background min-h-screen selection:bg-primary selection:text-primary-foreground transition-colors duration-700 relative overflow-hidden">
      {/* 3D Ambient Background Blobs */}
      <div className="absolute top-[-10%] right-[-5%] w-[50vw] h-[50vw] rounded-full bg-gradient-to-b from-primary-soft/60 to-transparent dark:from-primary-soft/30 blur-[100px] -z-10 pointer-events-none transition-colors duration-1000" />
      <div className="absolute bottom-[20%] left-[-10%] w-[40vw] h-[40vw] rounded-full bg-gradient-to-t from-primary-soft/40 to-transparent dark:from-primary-soft/40 blur-[80px] -z-10 pointer-events-none transition-colors duration-1000" />

      {/* Live `home.hero` slides crossfade on selection and auto-advance when
          multiple slides are available. */}
      <section
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onFocusCapture={() => setHasFocusWithin(true)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setHasFocusWithin(false);
        }}
        onTouchStart={(e) => setTouchStartX(e.touches[0].clientX)}
        onTouchEnd={(e) => {
          if (touchStartX == null || !slides.length) return;
          const dx = e.changedTouches[0].clientX - touchStartX;
          setTouchStartX(null);
          if (Math.abs(dx) < 50) return;
          goTo(index + (dx < 0 ? 1 : -1));
        }}
        className={`relative px-6 lg:px-8 max-w-[1400px] mx-auto w-[calc(100%-1.5rem)] sm:w-[calc(100%-2.5rem)] min-[1400px]:w-full z-10 ${
          slides.length > 0
            ? 'overflow-hidden rounded-[2rem] md:rounded-[3rem] my-6 md:my-10 min-h-[360px] md:min-h-[480px] flex flex-col justify-center'
            : 'pt-32 pb-20 md:pt-48 md:pb-32'
        }`}
      >
        {slides.length === 0 ? (
          <div className="max-w-4xl">
            <h1 className="text-foreground font-extrabold tracking-tighter text-5xl sm:text-7xl md:text-8xl lg:text-[10rem] leading-[0.9] sm:leading-[0.85] transition-colors duration-700 text-balance">
              {FALLBACK_HERO.titleTop}<br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-foreground to-muted-foreground">
                {FALLBACK_HERO.titleGradient}
              </span>
            </h1>
            <p className="mt-8 max-w-xl text-lg sm:text-xl text-muted-foreground font-medium leading-relaxed transition-colors duration-700">
              {FALLBACK_HERO.body}
            </p>
            <div className="mt-12 flex flex-wrap items-center gap-6">
              <Link
                to={FALLBACK_HERO.ctaLink}
                className="bg-primary text-primary-foreground px-10 py-4 rounded-full text-sm font-bold tracking-widest uppercase hover:scale-105 hover:-translate-y-1 hover:shadow-[0_20px_40px_rgba(0,0,0,0.2)] dark:hover:shadow-[0_20px_40px_rgba(255,255,255,0.15)] transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)]"
              >
                {FALLBACK_HERO.ctaLabel}
              </Link>
              <Link
                to="/products"
                className="group flex items-center gap-3 text-sm font-bold tracking-widest uppercase text-foreground overflow-hidden transition-colors duration-700"
              >
                Explore New Arrivals
                <span className="block transform transition-transform duration-500 ease-out group-hover:translate-x-2">
                  →
                </span>
              </Link>
            </div>
          </div>
        ) : (
          <>
            <div className="grid flex-1">
              {slides.map((slide, i) => {
                const active = i === index;
                const desktopImage = (slide.image_url || slide.mobile_image_url || '').trim();
                const mobileImage = (slide.mobile_image_url || desktopImage).trim();
                const photoSlide = { ...slide, image_url: desktopImage, mobile_image_url: mobileImage };
                const visibleImage = isDesktop ? desktopImage : mobileImage;
                const imageReady = !!visibleImage && !!imgOk[`${slide.id}:${visibleImage}`];
                const layout = slide.layout_mode || 'overlay';
                const artwork = layout === 'artwork' && imageReady;
                const split = layout === 'split' || (layout === 'artwork' && !imageReady);
                const heading = i === 0 ? 'h1' : 'h2';
                return (
                  <div
                    key={slide.id}
                    className={`relative col-start-1 row-start-1 min-w-0 transition-opacity duration-700 ${
                      active ? 'opacity-100' : 'opacity-0 pointer-events-none'
                    }`}
                    aria-hidden={!active}
                    inert={!active}
                  >
                    {artwork ? (
                      <div className="relative aspect-[4/5] overflow-hidden rounded-[1.5rem] bg-muted md:aspect-[16/6] md:h-auto md:min-h-0 md:rounded-[2.5rem]">
                        <HeroLink
                          slide={slide}
                          className="absolute inset-0 block overflow-hidden rounded-[inherit] focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-[-4px] focus-visible:outline-primary"
                          aria-label={(slide.link_label || '').trim() || slide.title}
                        >
                          <HeroPhoto slide={photoSlide} ready className="absolute inset-0" alt={slide.image_alt || slide.title} fit="contain" />
                          {heading === 'h1' ? (
                            <h1 className="sr-only">{slide.title}</h1>
                          ) : (
                            <h2 className="sr-only">{slide.title}</h2>
                          )}
                          {slide.body && <span className="sr-only">{slide.body}</span>}
                        </HeroLink>
                      </div>
                    ) : split ? (
                      <div className="grid aspect-[4/5] grid-cols-1 grid-rows-[55%_45%] overflow-hidden rounded-[1.5rem] border border-border bg-background md:aspect-auto md:h-full md:min-h-[480px] md:grid-rows-none md:grid-cols-[.9fr_1.1fr] md:rounded-[2.5rem]">
                        <HeroCopy
                          slide={layout === 'artwork' ? { ...slide, layout_mode: 'split' } : slide}
                          heading={heading}
                          compact
                          className="relative z-10 flex min-h-0 flex-col items-start justify-center overflow-hidden bg-muted px-6 py-4 md:px-10 md:py-9 lg:px-14"
                        />
                        <div className="relative min-h-0 overflow-hidden bg-primary-soft">
                          {imageReady ? (
                            <HeroPhoto slide={photoSlide} ready className="absolute inset-0" alt={slide.image_alt || ''} />
                          ) : (
                            <div className="absolute inset-0 bg-gradient-to-br from-primary-soft via-muted to-background" aria-hidden="true" />
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="relative aspect-[4/5] overflow-hidden rounded-[1.5rem] bg-neutral-900 md:aspect-auto md:h-full md:min-h-[480px] md:rounded-[2.5rem]">
                        {imageReady && <HeroPhoto slide={photoSlide} ready className="absolute inset-0" alt="" />}
                        <div className="absolute inset-0 bg-gradient-to-r from-black/75 via-black/45 to-black/10" aria-hidden="true" />
                        <HeroCopy
                          slide={slide}
                          heading={heading}
                          inverted
                          compact
                          className="relative z-10 flex h-full min-h-0 max-w-3xl flex-col items-start justify-center overflow-hidden px-7 py-8 sm:px-12 md:min-h-[480px] md:px-16"
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {slides.length > 1 && (
              <div className="relative z-20 mt-4 flex items-center justify-center gap-2 md:mt-5">
                <button
                  type="button"
                  aria-label="Previous slide"
                  onClick={() => goTo(index - 1)}
                  className="flex h-11 w-11 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  <ChevronLeft size={20} />
                </button>
                <div className="flex justify-center gap-1" role="group" aria-label="Choose hero slide">
                  {slides.map((slide, i) => (
                    <button
                      key={slide.id}
                      type="button"
                      aria-label={`Show slide ${i + 1} of ${slides.length}`}
                      aria-pressed={i === index}
                      onClick={() => goTo(i)}
                      className="flex h-11 w-11 items-center justify-center rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                    >
                      <span className={`h-2.5 rounded-full transition-all ${i === index ? 'w-7 bg-primary' : 'w-2.5 bg-primary/40 hover:bg-primary/70'}`} />
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  aria-label="Next slide"
                  onClick={() => goTo(index + 1)}
                  className="flex h-11 w-11 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                >
                  <ChevronRight size={20} />
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {/* Featured Products */}
      <section className="relative max-w-[1400px] mx-auto px-6 lg:px-8 py-20 md:py-32 z-10">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-16">
          <div>
            <h2 className="text-4xl md:text-5xl font-extrabold text-foreground tracking-tight transition-colors duration-700">
              New arrivals
            </h2>
            <p className="text-muted-foreground font-medium mt-3 text-lg transition-colors duration-700">
              The latest additions to the collection.
            </p>
          </div>
          {!loading && (
            <Link
              to="/products"
              className="group flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-foreground pb-1 border-b-2 border-transparent hover:border-primary transition-all duration-300"
            >
              View Entire Catalog
            </Link>
          )}
        </div>

        {loading ? (
          <ProductGridSkeleton
            count={8}
            gridClassName="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8 md:gap-10"
          />
        ) : productError ? (
          <div className="rounded-2xl border border-border bg-card px-6 py-10 text-center">
            <p className="text-foreground font-semibold">Featured products couldn’t load.</p>
            <button
              type="button"
              onClick={() => retryProducts()}
              className="mt-4 rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground transition hover:bg-primary-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Try again
            </button>
          </div>
        ) : featuredProducts.length === 0 ? (
          <p className="rounded-2xl border border-border bg-card px-6 py-10 text-center text-muted-foreground">
            No products are available right now. Please check back soon.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8 md:gap-10">
            {featuredProducts.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </section>

      {/* Kept from the redesign: editorial browsing section */}
      <section className="relative max-w-[1400px] mx-auto px-6 lg:px-8 pb-20 md:pb-32 z-10">
        <div className="grid overflow-hidden rounded-[2rem] border border-border bg-primary-soft lg:grid-cols-[.85fr_1.15fr] lg:rounded-[2.75rem]">
          <div className="flex flex-col justify-center p-7 sm:p-12 lg:p-16">
            <p className="mb-5 text-[10px] font-bold uppercase tracking-[0.24em] text-accent">A better way to browse</p>
            <h2 className="max-w-lg text-balance text-4xl font-black leading-[0.95] tracking-[-0.06em] text-foreground sm:text-6xl">
              Find the pieces that feel like you.
            </h2>
            <p className="mt-6 max-w-md text-base font-medium leading-7 text-muted-foreground">
              Start with the essentials, stay for the details. Our collection is built to move easily between the everyday and the occasion.
            </p>
            <Link
              to="/products"
              className="group mt-8 inline-flex w-fit items-center gap-3 rounded-full bg-primary px-6 py-4 text-xs font-bold uppercase tracking-[0.16em] text-primary-foreground transition hover:-translate-y-1 hover:bg-primary-hover"
            >
              Shop your way
              <ArrowUpRight size={16} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
          </div>

          <div className="grid grid-cols-2 gap-3 p-3 sm:gap-4 sm:p-5 lg:grid-cols-3 lg:p-6">
            {EDITORIAL_CARDS.map((card) => {
              const product = featuredProducts[card.index];
              const image = getProductImage(product) || heroAsset;
              const href = product?.slug ? `/products/${product.slug}` : '/products';

              return (
                <Link
                  key={card.title}
                  to={href}
                  className="group/card relative min-h-[270px] overflow-hidden rounded-[1.5rem] bg-card sm:min-h-[350px]"
                >
                  <img
                    src={image}
                    alt={product?.name || card.title}
                    className="absolute inset-0 h-full w-full object-cover transition duration-700 group-hover/card:scale-105"
                    onError={(event) => {
                      event.currentTarget.src = heroAsset;
                    }}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-foreground/85 via-foreground/10 to-transparent" />
                  <div className="absolute inset-x-4 bottom-4 text-background sm:inset-x-5 sm:bottom-5">
                    <p className="text-[9px] font-bold uppercase tracking-[0.2em] opacity-75">{card.eyebrow}</p>
                    <h3 className="mt-2 text-lg font-bold tracking-tight sm:text-xl">{card.title}</h3>
                    <span className="mt-3 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.16em] opacity-0 transition group-hover/card:opacity-100">
                      Explore <ArrowUpRight size={13} />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      <Suspense fallback={null}>
        <Chatbot />
      </Suspense>
    </div>
  );
};

export default Home;
