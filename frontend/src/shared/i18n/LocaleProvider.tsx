'use client';

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { createT, defaultLocale, type Locale, type Translate } from './index';

interface LocaleContextValue {
  locale: Locale;
  t: Translate;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: defaultLocale,
  t: createT(defaultLocale),
});

// The root provider starts from the request's language. Once a person is signed in, their own
// setting is the language of everything, the parts mounted above the session too (the passkey
// prompt): SessionGate hands it up with `useAdoptLocale`, and the root provider takes it.
const AdoptContext = createContext<(locale: Locale | null) => void>(() => undefined);

export function LocaleProvider({ locale, adoptable = false, children }: { locale: Locale; adoptable?: boolean; children: ReactNode }) {
  const [adopted, setAdopted] = useState<Locale | null>(null);
  const shown = (adoptable ? adopted : null) ?? locale;
  const value = useMemo(() => ({ locale: shown, t: createT(shown) }), [shown]);
  // The page says which language it is in, for screen readers and the browser's own tools.
  useEffect(() => {
    if (adoptable) document.documentElement.lang = shown;
  }, [adoptable, shown]);
  const inner = <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
  return adoptable ? <AdoptContext.Provider value={setAdopted}>{inner}</AdoptContext.Provider> : inner;
}

/** Makes `locale` the language of the whole app, the root provider's included, while mounted. */
export function useAdoptLocale(locale: Locale): void {
  const adopt = useContext(AdoptContext);
  useEffect(() => {
    adopt(locale);
    return () => adopt(null);
  }, [adopt, locale]);
}

export function useLocale(): Locale {
  return useContext(LocaleContext).locale;
}

export function useT(): Translate {
  return useContext(LocaleContext).t;
}
