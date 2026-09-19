import en from '@/messages/en.json';
import sv from '@/messages/sv.json';

// One catalog per UI language (playbook 6.5). `sv` is typed against `en`, so a
// key missing in one language fails `tsc` as well as scripts/messages-check.mjs.
export const locales = ['en', 'sv'] as const;
export type Locale = (typeof locales)[number];
export type MessageKey = keyof typeof en;
export type Catalog = Record<MessageKey, string>;

export const catalogs: Record<Locale, Catalog> = { en, sv };

// BCP 47 tags for Intl. English users in the Nordics read day-month order,
// so `en` formats as en-GB, never en-US.
export const localeTags: Record<Locale, string> = { en: 'en-GB', sv: 'sv-SE' };

export function isLocale(value: string | undefined | null): value is Locale {
  return value !== undefined && value !== null && (locales as readonly string[]).includes(value);
}

const configured = process.env.NEXT_PUBLIC_DEFAULT_LOCALE;
export const defaultLocale: Locale = isLocale(configured) ? configured : 'en';
