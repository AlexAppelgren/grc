import { formatMessage, type MessageVars } from './format-message';
import { catalogs, defaultLocale, localeTags, type Locale, type MessageKey } from './messages';

export { defaultLocale, isLocale, locales, localeTags } from './messages';
export type { Locale, MessageKey } from './messages';
export type { MessageVars } from './format-message';

export type Translate = (key: MessageKey, vars?: MessageVars) => string;

// The typed `t`. Every user-facing string goes through here (playbook 6.5);
// ESLint refuses string literals in JSX so a component cannot skip it.
export function t(key: MessageKey, vars: MessageVars = {}, locale: Locale = defaultLocale): string {
  const message = catalogs[locale][key] ?? catalogs.en[key];
  return formatMessage(message, vars, localeTags[locale]);
}

export function createT(locale: Locale): Translate {
  return (key, vars) => t(key, vars, locale);
}
