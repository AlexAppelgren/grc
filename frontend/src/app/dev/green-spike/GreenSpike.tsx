'use client';

import { GdsButton } from '@sebgroup/green-core/react';
import { register as registerButtonTransitionalStyles } from '@sebgroup/green-core/components/button/button.trans.styles.js';
import { useEffect, useState } from 'react';

import { useT } from '@/shared/i18n/LocaleProvider';

// D-04 spike: one Green Core React component under `next start`. The click
// count proves hydration; the Playwright test clicks and reads it. Outcome
// recorded in frontend/docs/D-04-spike.md.
export function GreenSpike() {
  const t = useT();
  const [count, setCount] = useState(0);

  useEffect(() => {
    // Transitional styles are registered on the client only: the registry is
    // a module singleton that expects a DOM.
    registerButtonTransitionalStyles();
  }, []);

  return (
    <section className="mx-auto max-w-[60ch] p-8">
      <h1>{t('dev.spike.title')}</h1>
      <p className="mt-2 text-muted">{t('dev.spike.lede')}</p>
      <div className="mt-6">
        <GdsButton rank="primary" onClick={() => setCount((c) => c + 1)}>
          {t('dev.spike.button')}
        </GdsButton>
      </div>
      <p className="mt-4" data-testid="spike-count" aria-live="polite">
        {t('dev.spike.count', { count })}
      </p>
    </section>
  );
}
