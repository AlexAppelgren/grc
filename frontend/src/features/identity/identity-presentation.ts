import type { PillTone } from '@/components/ui/pill-tones';
import type { Passkey, PasskeyDeviceType, UserSession } from '@/features/identity/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { Translate } from '@/shared/i18n';

// Pills and derived text for the identity screens (design/screens/me-*.html,
// design/system/pills-and-labels.md). Tone comes from the kind or the slot,
// labels from the catalog; the screen renders what comes back.

export type PasskeyFacts = Pick<Passkey, 'deviceType'>;
export type SessionFacts = Pick<UserSession, 'current'>;

// A passkey's device type is a fixed kind: both are neutral facts.
export const passkeyDeviceTone: Record<PasskeyDeviceType, PillTone> = {
  multi_device: 'information',
  single_device: 'information',
};

export function presentPasskey(passkey: PasskeyFacts, t: Translate): PresentedPill[] {
  const tone = passkeyDeviceTone[passkey.deviceType];
  if (tone === undefined) return [];
  const label = passkey.deviceType === 'multi_device' ? t('me.passkeys.synced') : t('me.passkeys.deviceBound');
  return [{ key: `device:${passkey.deviceType}`, label, tone, order: 10 }];
}

export function presentSession(session: SessionFacts, t: Translate): PresentedPill[] {
  if (!session.current) return [];
  return [{ key: 'session:current', label: t('me.sessions.thisDevice'), tone: 'positive', order: 10 }];
}

const BROWSERS: readonly [RegExp, string][] = [
  [/Edg(e|A|iOS)?\//, 'Edge'],
  [/OPR\/|Opera/, 'Opera'],
  [/SamsungBrowser\//, 'Samsung Internet'],
  [/Firefox\/|FxiOS\//, 'Firefox'],
  [/CriOS\//, 'Chrome'],
  [/Chrome\//, 'Chrome'],
  [/Safari\//, 'Safari'],
];

const SYSTEMS: readonly [RegExp, string][] = [
  [/iPhone/, 'iPhone'],
  [/iPad/, 'iPad'],
  [/Android/, 'Android'],
  [/Windows/, 'Windows'],
  [/Mac OS X|Macintosh/, 'macOS'],
  [/CrOS/, 'ChromeOS'],
  [/Linux/, 'Linux'],
];

function firstMatch(table: readonly [RegExp, string][], userAgent: string): string | null {
  for (const [pattern, name] of table) if (pattern.test(userAgent)) return name;
  return null;
}

// "Chrome on Windows" from a user agent string; the raw string when nothing
// is recognised, and the catalog's unknown-device text when it is empty.
export function describeDevice(userAgent: string | null | undefined, t: Translate): string {
  const ua = (userAgent ?? '').trim();
  if (ua === '') return t('common.unknownDevice');
  const browser = firstMatch(BROWSERS, ua);
  const os = firstMatch(SYSTEMS, ua);
  if (browser !== null && os !== null) return t('common.on', { browser, os });
  return browser ?? os ?? (ua.length > 60 ? `${ua.slice(0, 57)}…` : ua);
}
