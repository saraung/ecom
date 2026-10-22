import { useEffect, useRef } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Standard modal behaviour for the storefront's ad-hoc dialogs:
 *   - Escape closes,
 *   - focus moves into the dialog and is restored on close,
 *   - Tab is trapped inside while open,
 *   - background scroll is locked.
 *
 * Usage:
 *   const dialogRef = useModalA11y(closeModal, isOpen);
 *   <div role="dialog" aria-modal="true" ref={dialogRef}>…</div>
 *
 * Pass `active` when the dialog element is rendered conditionally from the
 * same component (the hook lives at the component's top level).
 */
export function useModalA11y(onClose, active = true) {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);

  // Keep the latest handler without restarting the effect on every render.
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!active) return;

    const previouslyFocused = document.activeElement;
    const node = dialogRef.current;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current?.();
        return;
      }
      if (event.key !== 'Tab' || !node) return;

      const focusable = Array.from(node.querySelectorAll(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null
      );
      if (focusable.length === 0) {
        event.preventDefault();
        node.focus?.();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    if (node) {
      const firstFocusable = node.querySelector(FOCUSABLE);
      (firstFocusable || node).focus?.();
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [active]);

  return dialogRef;
}

export default useModalA11y;
