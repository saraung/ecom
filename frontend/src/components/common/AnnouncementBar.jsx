import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getContentBlocks } from '../../api/content';

const ROTATE_MS = 4000;

/**
 * Store-wide announcement strip (slot: announcement.bar).
 *
 * Backend-driven, current UI is the default:
 * - 0 live blocks → renders nothing (zero layout shift).
 * - 1 live block  → static strip, image optional.
 * - 2+ live blocks → auto-rotating slider (dots, pause on hover,
 *   first slide only when reduced-motion is preferred).
 *
 * Rendered in-flow below the fixed header (see Layout) — never overlaid.
 */
const AnnouncementBar = () => {
  const [slides, setSlides] = useState([]);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getContentBlocks(['announcement.bar'])
      .then((blocks) => {
        if (!cancelled) {
          setSlides(blocks['announcement.bar'] || []);
          setIndex(0);
        }
      })
      .catch(() => {
        if (!cancelled) setSlides([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(query.matches);
    const onChange = (e) => setReducedMotion(e.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    if (slides.length < 2 || paused || reducedMotion) return undefined;
    const timer = setInterval(() => {
      setIndex((i) => (i + 1) % slides.length);
    }, ROTATE_MS);
    return () => clearInterval(timer);
  }, [slides.length, paused, reducedMotion]);

  if (slides.length === 0) return null;

  const renderSlide = (block, active) => {
    const href = (block.link || '').trim();
    const isInternal = href.startsWith('/');
    const content = (
      <>
        {block.image_url && (
          <img
            src={block.image_url}
            alt=""
            className="inline-block h-5 w-auto max-w-[120px] object-contain mr-2 align-middle"
            onError={(e) => {
              e.currentTarget.style.display = 'none';
            }}
          />
        )}
        <span className="font-bold">{block.title}</span>
        {block.body && <span className="hidden sm:inline"> · {block.body}</span>}
        {block.link_label && href && (
          <span className="underline underline-offset-2 font-semibold"> {block.link_label}</span>
        )}
      </>
    );
    return (
      <div
        key={block.id}
        className={`transition-opacity duration-500 ${
          active ? 'opacity-100' : 'opacity-0 absolute inset-0 pointer-events-none'
        }`}
        aria-hidden={!active}
      >
        {href ? (
          isInternal ? (
            <Link to={href} className="hover:opacity-90 transition-opacity">
              {content}
            </Link>
          ) : (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="hover:opacity-90 transition-opacity"
            >
              {content}
            </a>
          )
        ) : (
          content
        )}
      </div>
    );
  };

  return (
    <div
      className="bg-primary text-primary-foreground text-center text-xs sm:text-sm font-medium px-4 py-2"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {slides.length === 1 ? (
        renderSlide(slides[0], true)
      ) : (
        <div className="relative min-w-0">
          {slides.map((block, i) => renderSlide(block, i === index))}
        </div>
      )}
    </div>
  );
};

export default AnnouncementBar;
