import enAuth from '@/messages/auth/en.json';
import svAuth from '@/messages/auth/sv.json';
import enBriefing from '@/messages/briefing/en.json';
import svBriefing from '@/messages/briefing/sv.json';
import enCommon from '@/messages/common/en.json';
import svCommon from '@/messages/common/sv.json';
import enConsole from '@/messages/console/en.json';
import svConsole from '@/messages/console/sv.json';
import enConsoleAgentKeys from '@/messages/console-agent-keys/en.json';
import svConsoleAgentKeys from '@/messages/console-agent-keys/sv.json';
import enConsoleChangeFacts from '@/messages/console-change-facts/en.json';
import svConsoleChangeFacts from '@/messages/console-change-facts/sv.json';
import enConsoleSources from '@/messages/console-sources/en.json';
import svConsoleSources from '@/messages/console-sources/sv.json';
import enDev from '@/messages/dev/en.json';
import svDev from '@/messages/dev/sv.json';
import enFootprint from '@/messages/footprint/en.json';
import svFootprint from '@/messages/footprint/sv.json';
import enInventory from '@/messages/inventory/en.json';
import svInventory from '@/messages/inventory/sv.json';
import enLibrary from '@/messages/library/en.json';
import svLibrary from '@/messages/library/sv.json';
import enMe from '@/messages/me/en.json';
import svMe from '@/messages/me/sv.json';
import enNav from '@/messages/nav/en.json';
import svNav from '@/messages/nav/sv.json';
import enRoadmap from '@/messages/roadmap/en.json';
import svRoadmap from '@/messages/roadmap/sv.json';
import enTenantAdmin from '@/messages/tenant-admin/en.json';
import svTenantAdmin from '@/messages/tenant-admin/sv.json';
import enToday from '@/messages/today/en.json';
import svToday from '@/messages/today/sv.json';
import enVocabularies from '@/messages/vocabularies/en.json';
import svVocabularies from '@/messages/vocabularies/sv.json';
import enWatch from '@/messages/watch/en.json';
import svWatch from '@/messages/watch/sv.json';

// One catalog per UI language (playbook 6.5), stored as one file pair per
// feature namespace under src/messages/<namespace>/ so that packages owning
// different screens edit different files. A namespace is listed here once;
// scripts/messages-check.mjs refuses a key claimed by two of them, so the
// merge below never silently drops copy. `sv` is typed against `en`, so a key
// missing in one language fails `tsc` as well as the check.
const en = {
  ...enAuth,
  ...enBriefing,
  ...enCommon,
  ...enConsole,
  ...enConsoleAgentKeys,
  ...enConsoleChangeFacts,
  ...enConsoleSources,
  ...enDev,
  ...enFootprint,
  ...enInventory,
  ...enLibrary,
  ...enMe,
  ...enNav,
  ...enRoadmap,
  ...enTenantAdmin,
  ...enToday,
  ...enVocabularies,
  ...enWatch,
};

const sv = {
  ...svAuth,
  ...svBriefing,
  ...svCommon,
  ...svConsole,
  ...svConsoleAgentKeys,
  ...svConsoleChangeFacts,
  ...svConsoleSources,
  ...svDev,
  ...svFootprint,
  ...svInventory,
  ...svLibrary,
  ...svMe,
  ...svNav,
  ...svRoadmap,
  ...svTenantAdmin,
  ...svToday,
  ...svVocabularies,
  ...svWatch,
};

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
