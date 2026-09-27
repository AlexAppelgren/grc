'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useSetSecurityPolicy } from '@/features/security-policy/hooks';
import { draftOf, fieldsAboveMaximum, parseLimit, type LimitField, type LimitsDraft } from '@/features/security-policy/session-limits';
import type { SecurityPolicy } from '@/features/security-policy/types';
import { useT } from '@/shared/i18n/LocaleProvider';

// Sessions (design/screens/admin-security.html, ID-08): the idle and the
// absolute limit, each with the platform maximum beside it. Save is a security
// change: the api client opens the passkey prompt on the server's
// step_up_required. Above a maximum the server answers 422
// above_platform_maximum, drawn under the field it names from its code.

export function SessionPolicyPanel({ policy }: { policy: SecurityPolicy }) {
  const t = useT();
  const save = useSetSecurityPolicy();
  const [draft, setDraft] = useState<LimitsDraft>(() => draftOf(policy));
  const [invalid, setInvalid] = useState<LimitField[]>([]);
  const [saved, setSaved] = useState(false);
  const above = save.isError ? fieldsAboveMaximum(save.error) : [];

  const change = (field: LimitField, value: string) => {
    setSaved(false);
    setInvalid((current) => current.filter((f) => f !== field));
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    const idle = parseLimit(draft.sessionIdleMinutes);
    const absolute = parseLimit(draft.sessionAbsoluteHours);
    const refused: LimitField[] = [...(idle === 'invalid' ? ['sessionIdleMinutes' as const] : []), ...(absolute === 'invalid' ? ['sessionAbsoluteHours' as const] : [])];
    setInvalid(refused);
    if (idle === 'invalid' || absolute === 'invalid') return;
    save.mutate({ sessionIdleMinutes: idle, sessionAbsoluteHours: absolute }, { onSuccess: () => setSaved(true) });
  };

  const cancel = () => {
    save.reset();
    setSaved(false);
    setInvalid([]);
    setDraft(draftOf(policy));
  };

  const errorOf = (field: LimitField, aboveText: string): string | undefined =>
    invalid.includes(field) ? t('admin.security.sessions.invalid') : above.includes(field) ? aboveText : undefined;
  const idleError = errorOf('sessionIdleMinutes', t('admin.security.sessions.idleAbove', { max: policy.sessionIdleMinutesMax }));
  const absoluteError = errorOf('sessionAbsoluteHours', t('admin.security.sessions.absoluteAbove', { max: policy.sessionAbsoluteHoursMax }));

  return (
    <form onSubmit={submit} noValidate aria-busy={save.isPending} data-session-policy="">
      <Panel title={t('admin.security.sessions.title')}>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field id="security-idle" label={t('admin.security.sessions.idle')} hint={t('admin.security.sessions.idleHint', { max: policy.sessionIdleMinutesMax, default: policy.sessionIdleMinutesDefault })} error={idleError}>
            <TextInput
              id="security-idle"
              inputMode="numeric"
              value={draft.sessionIdleMinutes}
              onChange={(e) => change('sessionIdleMinutes', e.target.value)}
              aria-invalid={idleError !== undefined ? true : undefined}
              aria-describedby={idleError !== undefined ? 'security-idle-hint security-idle-error' : 'security-idle-hint'}
            />
          </Field>
          <Field id="security-absolute" label={t('admin.security.sessions.absolute')} hint={t('admin.security.sessions.absoluteHint', { max: policy.sessionAbsoluteHoursMax, default: policy.sessionAbsoluteHoursDefault })} error={absoluteError}>
            <TextInput
              id="security-absolute"
              inputMode="numeric"
              value={draft.sessionAbsoluteHours}
              onChange={(e) => change('sessionAbsoluteHours', e.target.value)}
              aria-invalid={absoluteError !== undefined ? true : undefined}
              aria-describedby={absoluteError !== undefined ? 'security-absolute-hint security-absolute-error' : 'security-absolute-hint'}
            />
          </Field>
        </div>
        <p className="text-meta text-muted">{t('admin.security.sessions.applies')}</p>
        {save.isError && above.length === 0 ? <ProblemAlert error={save.error} codes={{ step_up_required: t('admin.security.stepUpCancelled') }} /> : null}
        {saved && !save.isPending ? <StatusLine tone="positive">{t('admin.security.saved')}</StatusLine> : null}
        <ButtonBar>
          <Button type="button" variant="outline" disabled={save.isPending} onClick={cancel}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {t('common.save')}
          </Button>
        </ButtonBar>
        <p className="mt-2 text-meta text-muted">{t('admin.security.saveHint')}</p>
      </Panel>
    </form>
  );
}
