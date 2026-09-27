'use client';

import { useId, useState, type KeyboardEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { controlClass, Field } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { cn } from '@/shared/utils/cn';
import { formatLongDate } from '@/shared/utils/format';
import { problemFrom } from '@/shared/utils/problem';

import type { OutOfOffice, Person } from './api';
import { useOutOfOffice, usePeople, useSetOutOfOffice } from './hooks';

// Out of office (design/screens/me-out-of-office.html; TEN-04, TEN-S4): the
// person's own last day away and the delegate who receives their approval
// requests and reminders meanwhile, or, while away, the window with End now.
// The date is a plain date on the bank's calendar, so today and the earliest
// choice are the bank's today, never the device's. Refusals render from the
// problem's code under the field they belong to; the delegate gains nothing,
// the server checks what they may approve.

/** The calendar day it is now in `timeZone`, as YYYY-MM-DD. */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone }).format(now);
}

type FieldErrors = { untilDate?: string; delegateId?: string };

/** Which field a refusal belongs to, from its code and the `errors[].field` it names. */
function fieldOf(error: unknown): 'untilDate' | 'delegateId' | null {
  const problem = problemFrom(error);
  if (problem?.code === 'delegate_cannot_approve') return 'delegateId';
  if (problem?.code !== 'validation_error') return null;
  for (const entry of problem.errors ?? []) {
    const field = typeof entry === 'object' && entry !== null ? (entry as { field?: unknown }).field : undefined;
    if (field === 'untilDate' || field === 'delegateId') return field;
  }
  return null;
}

function DelegatePicker({ id, people, value, onChange, error, hint }: { id: string; people: Person[]; value: Person | null; onChange: (person: Person | null) => void; error?: string; hint: string }) {
  const t = useT();
  const listId = useId();
  const [text, setText] = useState(value?.name ?? '');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const needle = text.trim().toLocaleLowerCase();
  const matches = people.filter((person) => person.name.toLocaleLowerCase().includes(needle));

  const choose = (person: Person) => {
    onChange(person);
    setText(person.name);
    setOpen(false);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setOpen(true);
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((current) => (matches.length === 0 ? 0 : (current + step + matches.length) % matches.length));
    } else if (event.key === 'Enter' && open && matches[active] !== undefined) {
      event.preventDefault();
      choose(matches[active]);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <Field id={id} label={t('me.outOfOffice.delegate')} hint={hint} error={error}>
      <div className="relative max-w-[360px]">
        <input
          id={id}
          role="combobox"
          autoComplete="off"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && matches[active] !== undefined ? `${listId}-${matches[active].id}` : undefined}
          aria-describedby={error !== undefined ? `${id}-error` : `${id}-hint`}
          aria-invalid={error !== undefined}
          className={controlClass}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
            setOpen(true);
            if (value !== null) onChange(null);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
        />
        {open ? (
          matches.length === 0 ? (
            <p role="status" className="mt-1 rounded-control border border-line bg-surface px-2 py-1.5 text-meta text-muted">
              {t('me.outOfOffice.noMatch', { text: text.trim() })}
            </p>
          ) : (
            <ul id={listId} role="listbox" aria-label={t('me.outOfOffice.people')} className="m-0 mt-1 max-h-60 list-none overflow-y-auto rounded-control border border-line bg-surface p-1">
              {matches.map((person, index) => (
                <li
                  key={person.id}
                  id={`${listId}-${person.id}`}
                  role="option"
                  aria-selected={index === active}
                  className={cn('cursor-pointer rounded-control px-2 py-1.5 font-medium', index === active && 'bg-accent')}
                  // Chosen before the input's blur closes the list.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    choose(person);
                  }}
                >
                  {person.name}
                </li>
              ))}
            </ul>
          )
        ) : null}
      </div>
    </Field>
  );
}

function SetForm({ selfId, onAlreadyAway }: { selfId: string | undefined; onAlreadyAway: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const people = usePeople();
  const save = useSetOutOfOffice();
  const [until, setUntil] = useState('');
  const [delegate, setDelegate] = useState<Person | null>(null);
  const today = todayIn(ctx.timeZone);

  const refusedField = save.isError ? fieldOf(save.error) : null;
  const errors: FieldErrors = {};
  if (refusedField === 'untilDate') errors.untilDate = t('me.outOfOffice.untilInvalid');
  if (refusedField === 'delegateId') {
    errors.delegateId =
      problemFrom(save.error)?.code === 'delegate_cannot_approve'
        ? t('me.outOfOffice.delegateCannotApprove', { name: people.data?.find((person) => person.id === save.variables?.delegateId)?.name ?? '' })
        : t('me.outOfOffice.delegateInvalid');
  }
  const alreadyAway = save.isError && problemFrom(save.error)?.code === 'already_delegated';

  return (
    <form
      className="max-w-[560px] rounded-card border border-line bg-surface p-4"
      data-out-of-office-form=""
      onSubmit={(event) => {
        event.preventDefault();
        if (delegate !== null && until !== '') save.mutate({ untilDate: until, delegateId: delegate.id });
      }}
    >
      <Field id="ooo-until" label={t('me.outOfOffice.until')} hint={t('me.outOfOffice.untilHint', { timeZone: ctx.timeZone })} error={errors.untilDate}>
        <input
          id="ooo-until"
          type="date"
          min={today}
          required
          value={until}
          onChange={(event) => setUntil(event.target.value)}
          aria-describedby={errors.untilDate !== undefined ? 'ooo-until-error' : 'ooo-until-hint'}
          aria-invalid={errors.untilDate !== undefined}
          className={cn(controlClass, 'max-w-[220px] tabular-nums')}
        />
      </Field>
      {people.isError ? (
        <ProblemAlert error={people.error} />
      ) : (
        <DelegatePicker
          id="ooo-delegate"
          people={(people.data ?? []).filter((person) => person.id !== selfId)}
          value={delegate}
          onChange={setDelegate}
          error={errors.delegateId}
          hint={t('me.outOfOffice.delegateHint')}
        />
      )}
      <div className="mt-4 rounded-control bg-subtle px-3 py-2.5">
        <p className="m-0">{t('me.outOfOffice.what')}</p>
        <p className="m-0 mt-1">{t('me.outOfOffice.stays')}</p>
      </div>
      {alreadyAway ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p role="alert" className="m-0 text-meta text-negative">
            {t('me.outOfOffice.alreadyAway')}
          </p>
          <Button variant="outline" size="small" onClick={onAlreadyAway}>
            {t('me.outOfOffice.showIt')}
          </Button>
        </div>
      ) : save.isError && refusedField === null ? (
        <ProblemAlert error={save.error} />
      ) : null}
      <ButtonBar>
        <Button type="submit" disabled={save.isPending || delegate === null || until === ''}>
          {t('me.outOfOffice.set')}
        </Button>
      </ButtonBar>
    </form>
  );
}

function AwayPanel({ absence, onEnded }: { absence: OutOfOffice; onEnded: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const end = useSetOutOfOffice();
  return (
    <Panel className="max-w-[560px]" aria-labelledby="ooo-away" data-away="">
      <h2 id="ooo-away" className="mb-1 text-title">
        {t('me.outOfOffice.awayTitle')}
      </h2>
      <p className="mb-2">
        {t('me.outOfOffice.awayBody', { date: formatLongDate(absence.untilDate ?? '', ctx), name: absence.delegate?.name ?? '' })}
      </p>
      <Meta>
        <span>{t('me.outOfOffice.stays')}</span>
      </Meta>
      {end.isError ? <ProblemAlert error={end.error} /> : null}
      <ButtonBar>
        <Button variant="outline" disabled={end.isPending} onClick={() => end.mutate({ untilDate: null, delegateId: null }, { onSuccess: onEnded })}>
          {t('me.outOfOffice.endNow')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

export function OutOfOfficeScreen() {
  const t = useT();
  const { me } = useSession();
  const absence = useOutOfOffice();
  const [back, setBack] = useState(false);

  return (
    <>
      <PageHead title={t('me.outOfOffice.title')} lede={t('me.outOfOffice.lede')} />
      {absence.isPending ? (
        <LoadingState />
      ) : absence.isError ? (
        <ErrorState title={t('me.outOfOffice.errorTitle')} onRetry={() => void absence.refetch()} />
      ) : absence.data.away ? (
        <AwayPanel absence={absence.data} onEnded={() => setBack(true)} />
      ) : (
        <>
          {back ? <StatusLine tone="positive">{t('me.outOfOffice.back')}</StatusLine> : null}
          <SetForm selfId={me?.user.id} onAlreadyAway={() => void absence.refetch()} />
        </>
      )}
    </>
  );
}
