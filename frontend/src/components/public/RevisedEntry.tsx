'use client';

import { type ReactNode, useEffect, useRef } from 'react';

// A dictionary entry the product replaces (design/public/, the Lexicon
// direction): its strike is drawn and its correction written once, when the
// entry comes into view. data-reveal drives the CSS in PublicPage.tsx: without
// it, as the server sends the page, everything is already drawn, and under
// prefers-reduced-motion the CSS shows the finished state whatever it says.
export function RevisedEntry({ id, labelledBy, className, children }: { id: string; labelledBy: string; className: string; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const entry = ref.current;
    if (entry === null || !('IntersectionObserver' in window)) return;
    entry.dataset.reveal = 'waiting';
    // Seen once its top passes two thirds of the way up the screen, however tall it is.
    const observer = new IntersectionObserver(
      (changes) => {
        if (!changes.some((change) => change.isIntersecting)) return;
        entry.dataset.reveal = 'seen';
        observer.disconnect();
      },
      { rootMargin: '0px 0px -35% 0px' },
    );
    observer.observe(entry);
    return () => observer.disconnect();
  }, []);

  return (
    <section ref={ref} id={id} aria-labelledby={labelledBy} className={className}>
      {children}
    </section>
  );
}
