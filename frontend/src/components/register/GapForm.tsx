'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { ProblemAlert } from '@/components/ui/States';
import { gapProblemCopy } from '@/features/gaps/gap-view';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useCreateGap, useUpdateGap } from '@/features/register/hooks';
import type { RegisterGap } from '@/features/register/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Record a gap" and its Edit (design/screens/tenant-gaps.html, state 13;
// REG-03). The obligation is fixed; the lists are the bank's own rows and the
// form sends their keys. An owner is a person or a team, never both: the
// people reference arrives with the organisation screens, so a new gap is
// owned by the person recording it or by one of the bank's teams, and Edit
// keeps whoever owns it now. A gap is recorded on the obligation as a whole
// until the register entry can name its legal entities to pick from. The
// server checks every field again.

type Owner = `person:${string}` | `team:${string}` | '';

function ownerOf(gap: RegisterGap | null, meId: string | null): Owner {
  if (gap === null) return meId === null ? '' : `person:${meId}`;
  if (gap.owner !== null) return `person:${gap.owner.id}`;
  return gap.ownerTeam === null ? '' : `team:${gap.ownerTeam.key}`;
}

function ownerBody(owner: Owner): { ownerId?: string; ownerTeam?: string } {
  if (owner.startsWith('person:')) return { ownerId: owner.slice('person:'.length) };
  if (owner.startsWith('team:')) return { ownerTeam: owner.slice('team:'.length) };
  return {};
}

/** Today in the bank's zone, as the plain date a date input speaks. */
function localToday(timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

const nullIfBlank = (value: string) => (value.trim() === '' ? null : value.trim());

export function GapForm({
  obligationId,
  obligationTitle,
  gap,
  onClose,
  onDone,
}: {
  obligationId: string;
  obligationTitle: string;
  /** The gap to edit; null records a new one. */
  gap: RegisterGap | null;
  onClose: () => void;
  onDone: (saved: RegisterGap) => void;
}) {
  const t = useT();
  const { me } = useSession();
  const meId = me?.user.id ?? null;
  const today = localToday(useFormatContext().timeZone);
  const severities = useVocabularyValues('risk_rating');
  const sources = useVocabularyValues('gap_source', false, gap === null);
  const teams = useVocabularyValues('team');
  const create = useCreateGap(obligationId);
  const update = useUpdateGap();
  const write = gap === null ? create : update;

  const [title, setTitle] = useState(gap?.title ?? '');
  const [description, setDescription] = useState(gap?.description ?? '');
  const [severity, setSeverity] = useState(gap?.severity.key ?? '');
  const [source, setSource] = useState('');
  const [owner, setOwner] = useState<Owner>(ownerOf(gap, meId));
  const [target, setTarget] = useState(gap?.targetDate ?? '');
  const [plan, setPlan] = useState(gap?.remediation ?? '');
  const [tried, setTried] = useState(false);

  const severityRows = severities.data ?? [];
  const sourceRows = sources.data ?? [];
  const chosenSeverity = severity === '' ? (severityRows[0]?.key ?? '') : severity;
  const chosenSource = source === '' ? (sourceRows[0]?.key ?? '') : source;
  const titleError = tried && title.trim() === '' ? t('gaps.form.titleRequired') : undefined;
  // A date already set may stay as it is; a new or changed one starts today or later.
  const targetError = tried && target !== '' && target !== gap?.targetDate && target < today ? t('gaps.form.targetPast') : undefined;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (title.trim() === '' || (target !== '' && target !== gap?.targetDate && target < today)) return;
    const common = {
      title: title.trim(),
      description: nullIfBlank(description),
      severity: chosenSeverity,
      targetDate: target === '' ? null : target,
      remediation: nullIfBlank(plan),
    };
    if (gap === null) {
      create.mutate(
        { ...common, source: chosenSource, ...ownerBody(owner) },
        { onSuccess: onDone },
      );
    } else {
      const ownerChanged = owner !== ownerOf(gap, meId);
      update.mutate({ gapId: gap.id, body: { ...common, ...(ownerChanged ? ownerBody(owner) : {}) }, version: gap.version }, { onSuccess: onDone });
    }
  };

  const personOwner = gap?.owner ?? null;
  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={t(gap === null ? 'gaps.form.createTitle' : 'gaps.form.editTitle')} description={obligationTitle}>
      <form onSubmit={submit} noValidate aria-busy={write.isPending} data-gap-form="">
        <Field id="gap-title" label={t('gaps.form.title')} error={titleError}>
          <TextInput id="gap-title" value={title} maxLength={300} aria-invalid={titleError !== undefined} aria-describedby={titleError === undefined ? undefined : 'gap-title-error'} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field id="gap-description" label={t('gaps.form.description')}>
          <TextArea id="gap-description" value={description} placeholder={t('gaps.form.descriptionPlaceholder')} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="grid gap-x-3 md:grid-cols-2">
          <Field id="gap-severity" label={t('gaps.form.severity')}>
            <Select id="gap-severity" value={chosenSeverity} onChange={(e) => setSeverity(e.target.value)}>
              {severityRows.map((row) => (
                <option key={row.key} value={row.key}>
                  {row.label}
                </option>
              ))}
            </Select>
          </Field>
          {gap === null ? (
            <Field id="gap-source" label={t('gaps.form.source')}>
              <Select id="gap-source" value={chosenSource} onChange={(e) => setSource(e.target.value)}>
                {sourceRows.map((row) => (
                  <option key={row.key} value={row.key}>
                    {row.label}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}
          <Field id="gap-owner" label={t('gaps.form.owner')} hint={t('gaps.form.ownerHint')}>
            <Select id="gap-owner" value={owner} aria-describedby="gap-owner-hint" onChange={(e) => setOwner(e.target.value as Owner)}>
              {meId === null ? null : <option value={`person:${meId}`}>{t('gaps.form.ownerMe')}</option>}
              {personOwner !== null && personOwner.id !== meId ? <option value={`person:${personOwner.id}`}>{personOwner.name}</option> : null}
              {(teams.data ?? []).map((row) => (
                <option key={row.key} value={`team:${row.key}`}>
                  {t('gaps.form.ownerTeam', { team: row.label })}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="gap-target" label={t('gaps.form.target')} error={targetError}>
            <TextInput id="gap-target" type="date" value={target} min={today} aria-invalid={targetError !== undefined} aria-describedby={targetError === undefined ? undefined : 'gap-target-error'} onChange={(e) => setTarget(e.target.value)} />
          </Field>
        </div>
        <Field id="gap-plan" label={t('gaps.form.plan')}>
          <TextArea id="gap-plan" value={plan} placeholder={t('gaps.form.planPlaceholder')} onChange={(e) => setPlan(e.target.value)} />
        </Field>
        {write.isError ? <ProblemAlert error={write.error} codes={gapProblemCopy(t)} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={write.isPending || chosenSeverity === '' || (gap === null && chosenSource === '')}>
            {t(gap === null ? 'gaps.form.create' : 'gaps.form.save')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}
