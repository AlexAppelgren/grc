'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';

import { createT, defaultLocale, type Locale, type Translate } from './index';

interface LocaleContextValue {
  locale: Locale;
  t: Translate;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: defaultLocale,
  t: createT(defaultLocale),
});

export function LocaleProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const value = useMemo(() => ({ locale, t: createT(locale) }), [locale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return useContext(LocaleContext).locale;
}

export function useT(): Translate {
  return useContext(LocaleContext).t;
}
