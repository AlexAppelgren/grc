import enAuth from '@/messages/auth/en.json';
import svAuth from '@/messages/auth/sv.json';
import enBriefing from '@/messages/briefing/en.json';
import svBriefing from '@/messages/briefing/sv.json';
import enCalendarFeeds from '@/messages/calendar-feeds/en.json';
import svCalendarFeeds from '@/messages/calendar-feeds/sv.json';
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
// c8-fe-obligation-shell: the obligation page's register panels, one namespace each.
import enObligationApplicability from '@/messages/obligation-applicability/en.json';
import svObligationApplicability from '@/messages/obligation-applicability/sv.json';
import enObligationStatus from '@/messages/obligation-status/en.json';
import svObligationStatus from '@/messages/obligation-status/sv.json';
import enObligationGaps from '@/messages/obligation-gaps/en.json';
import svObligationGaps from '@/messages/obligation-gaps/sv.json';
import enObligationLinks from '@/messages/obligation-links/en.json';
import svObligationLinks from '@/messages/obligation-links/sv.json';
import enObligationParticipants from '@/messages/obligation-participants/en.json';
import svObligationParticipants from '@/messages/obligation-participants/sv.json';
import enObligationUnits from '@/messages/obligation-units/en.json';
import svObligationUnits from '@/messages/obligation-units/sv.json';
import enObligationHistory from '@/messages/obligation-history/en.json';
import svObligationHistory from '@/messages/obligation-history/sv.json';
import enObligationTags from '@/messages/obligation-tags/en.json';
import svObligationTags from '@/messages/obligation-tags/sv.json';
import enPublic from '@/messages/public/en.json';
import svPublic from '@/messages/public/sv.json';
import enRoadmap from '@/messages/roadmap/en.json';
import svRoadmap from '@/messages/roadmap/sv.json';
import enSearch from '@/messages/search/en.json';
import svSearch from '@/messages/search/sv.json';
import enTenantAdmin from '@/messages/tenant-admin/en.json';
import svTenantAdmin from '@/messages/tenant-admin/sv.json';
import enToday from '@/messages/today/en.json';
import svToday from '@/messages/today/sv.json';
import enVocabularies from '@/messages/vocabularies/en.json';
import svVocabularies from '@/messages/vocabularies/sv.json';
import enWatch from '@/messages/watch/en.json';
import svWatch from '@/messages/watch/sv.json';
// The case panels' catalogs (c9-fe-cases-shell).
import enCases from '@/messages/cases/en.json';
import svCases from '@/messages/cases/sv.json';
import enCaseTriage from '@/messages/case-triage/en.json';
import svCaseTriage from '@/messages/case-triage/sv.json';
import enCaseAssessment from '@/messages/case-assessment/en.json';
import svCaseAssessment from '@/messages/case-assessment/sv.json';
import enCaseActions from '@/messages/case-actions/en.json';
import svCaseActions from '@/messages/case-actions/sv.json';
import enCaseEvidence from '@/messages/case-evidence/en.json';
import svCaseEvidence from '@/messages/case-evidence/sv.json';
import enCaseSignoff from '@/messages/case-signoff/en.json';
import svCaseSignoff from '@/messages/case-signoff/sv.json';
import enCaseFile from '@/messages/case-file/en.json';
import svCaseFile from '@/messages/case-file/sv.json';
import enCaseParticipants from '@/messages/case-participants/en.json';
import svCaseParticipants from '@/messages/case-participants/sv.json';

// One catalog per UI language (playbook 6.5), stored as one file pair per
// feature namespace under src/messages/<namespace>/ so that packages owning
// different screens edit different files. A namespace is listed here once;
// scripts/messages-check.mjs refuses a key claimed by two of them, so the
// merge below never silently drops copy. `sv` is typed against `en`, so a key
// missing in one language fails `tsc` as well as the check.
const en = {
  ...enAuth,
  ...enBriefing,
  ...enCalendarFeeds,
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
  // c8-fe-obligation-shell
  ...enObligationApplicability,
  ...enObligationStatus,
  ...enObligationGaps,
  ...enObligationLinks,
  ...enObligationParticipants,
  ...enObligationUnits,
  ...enObligationHistory,
  ...enObligationTags,
  ...enPublic,
  ...enRoadmap,
  ...enSearch,
  ...enTenantAdmin,
  ...enToday,
  ...enVocabularies,
  ...enWatch,
  ...enCases,
  ...enCaseTriage,
  ...enCaseAssessment,
  ...enCaseActions,
  ...enCaseEvidence,
  ...enCaseSignoff,
  ...enCaseFile,
  ...enCaseParticipants,
};

const sv = {
  ...svAuth,
  ...svBriefing,
  ...svCalendarFeeds,
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
  // c8-fe-obligation-shell
  ...svObligationApplicability,
  ...svObligationStatus,
  ...svObligationGaps,
  ...svObligationLinks,
  ...svObligationParticipants,
  ...svObligationUnits,
  ...svObligationHistory,
  ...svObligationTags,
  ...svPublic,
  ...svRoadmap,
  ...svSearch,
  ...svTenantAdmin,
  ...svToday,
  ...svVocabularies,
  ...svWatch,
  ...svCases,
  ...svCaseTriage,
  ...svCaseAssessment,
  ...svCaseActions,
  ...svCaseEvidence,
  ...svCaseSignoff,
  ...svCaseFile,
  ...svCaseParticipants,
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
