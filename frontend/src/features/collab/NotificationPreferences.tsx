'use client';

import { Panel } from '@/components/ui/Panel';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useSession } from '@/features/identity/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';
import { NETWORK_PROBLEM_CODE } from '@/shared/utils/problem';

import { useUpdateNotificationPrefs } from './hooks';
import type { NotificationPrefs } from './types';

// "What reaches you" (design/screens/tenant-notifications.html, blocks 10 and
// 11; COL-02): one switch per kind a person may turn off, saved at once on
// change with no Save button. Each save sends the whole set of switches with
// the one flipped; the switch moves before the answer and a refused save puts
// it back (hooks.ts) and says so. Escalations are the bank's to decide, so
// they are held on with the read-only glyph, never a greyed switch.

type PrefKey = keyof NotificationPrefs;

// Every switch a person may turn off, in the card's order, with its catalog phrases.
export const MUTABLE_PREFS: readonly { key: PrefKey; label: MessageKey; hint: MessageKey }[] = [
  { key: 'mentions', label: 'collab.prefs.mentions', hint: 'collab.prefs.mentionsHint' },
  { key: 'assignments', label: 'collab.prefs.assignments', hint: 'collab.prefs.assignmentsHint' },
  { key: 'reminders', label: 'collab.prefs.reminders', hint: 'collab.prefs.remindersHint' },
  { key: 'weeklyDigest', label: 'collab.prefs.weeklyDigest', hint: 'collab.prefs.weeklyDigestHint' },
  { key: 'weeklyBriefing', label: 'collab.prefs.weeklyBriefing', hint: 'collab.prefs.weeklyBriefingHint' },
];

function Switch({ id, checked, disabled, onToggle }: { id: string; checked: boolean; disabled: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={id}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        'relative h-5 w-9 shrink-0 rounded-control border p-0 disabled:opacity-45',
        'after:absolute after:top-px after:size-4 after:rounded-[4px] after:transition-[left] after:content-[""]',
        checked ? 'border-button bg-button after:left-[17px] after:bg-on-button' : 'border-line-strong bg-surface after:left-px after:bg-line-strong',
      )}
    />
  );
}

function HeldGlyph() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="size-4 fill-none stroke-current" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
      <rect x="1.5" y="1.5" width="13" height="13" rx="3" />
      <path d="M4.5 8.2l2.3 2.3 4.7-4.9" />
    </svg>
  );
}

function PrefRow({ id, label, hint, children }: { id?: string; label: string; hint: string; children: React.ReactNode }) {
  return (
    <li className="flex items-center justify-between gap-4 border-b border-line py-3 last:border-b-0">
      <div>
        <span id={id} className="block font-medium">
          {label}
        </span>
        <span className="block max-w-[60ch] text-meta text-muted">{hint}</span>
      </div>
      {children}
    </li>
  );
}

export function NotificationPreferences() {
  const t = useT();
  const { me } = useSession();
  const update = useUpdateNotificationPrefs();
  const prefs = me?.notificationPrefs;
  // A platform session belongs to no bank and has no switches.
  if (prefs == null) return null;

  return (
    <Panel className="mt-6" aria-labelledby="prefs-title" data-notification-prefs="">
      <h2 id="prefs-title" className="mb-1">
        {t('collab.prefs.title')}
      </h2>
      <p className="mb-2 text-meta text-muted">{t('collab.prefs.lede')}</p>
      <ul className="m-0 list-none p-0">
        {MUTABLE_PREFS.map(({ key, label, hint }) => (
          <PrefRow key={key} id={`pref-${key}`} label={t(label)} hint={t(hint)}>
            <Switch id={`pref-${key}`} checked={prefs[key]} disabled={update.isPending} onToggle={() => update.mutate({ ...prefs, [key]: !prefs[key] })} />
          </PrefRow>
        ))}
        <PrefRow label={t('collab.prefs.escalations')} hint={t('collab.prefs.escalationsHint')}>
          <span className="inline-flex shrink-0 items-center gap-1.5" data-pref-held="escalation">
            <HeldGlyph />
            <span>{t('collab.prefs.alwaysOn')}</span>
          </span>
        </PrefRow>
      </ul>
      {update.isPending ? (
        <StatusLine>{t('collab.prefs.saving')}</StatusLine>
      ) : update.isError ? (
        <ProblemAlert error={update.error} codes={{ [NETWORK_PROBLEM_CODE]: t('collab.prefs.saveFailed') }} />
      ) : update.isSuccess ? (
        <StatusLine tone="positive">{t('collab.prefs.saved')}</StatusLine>
      ) : null}
    </Panel>
  );
}
