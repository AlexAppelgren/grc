'use client';

import { useId, useState, type KeyboardEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextArea, TextInput, controlClass } from '@/components/ui/Field';
import { Pill } from '@/components/ui/Pill';
import { PillRow } from '@/components/ui/PillRow';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useCreateValue, useSuggestValue, useVocabularyValues } from '@/features/vocabularies/hooks';
import type { VocabularyRow } from '@/features/vocabularies/types';
import {
  exactDuplicateFrom,
  listLabel,
  nearDuplicateFrom,
  nearMatches,
  presentSuggestedValue,
  presentVocabularyValue,
  usageText,
} from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';

// The one picker for every vocabulary (design/screens/picker-create-or-suggest.html).
// The combobox lists existing values, offers the near match before anything
// else, then one last option by the list's tier:
//
//   - a TENANT list, for a holder of `vocab.manage`: Create, expanded in place
//     for the usage note (VOC-01).
//   - a TENANT list, for everyone else: Suggest, expanded the same way (VOC-03).
//     The suggestion waits in the admin's Suggested tab and is not picked; the
//     field marks it until the picker is used again.
//   - a LIBRARY list, for a holder of `proposals.create`: Propose, which
//     becomes a proposal the platform console reviews (VOC-07). The value is
//     used once approved.
//
// The server refuses a create or a suggestion two ways, rendered in place by
// code with the value to use (AC-VOC3): 409 duplicate_key, the value exists;
// 422 near_duplicate, "Did you mean …?". Nothing is offered until the
// permission list is known.

const VOCAB_MANAGE = 'vocab.manage';
const PROPOSALS_CREATE = 'proposals.create';

type LastOption = 'create' | 'suggest' | 'propose' | null;

export function lastOption(tier: 'tenant' | 'library', permissions: readonly string[] | null): LastOption {
  if (permissions === null) return null;
  if (tier === 'library') return permissions.includes(PROPOSALS_CREATE) ? 'propose' : null;
  return permissions.includes(VOCAB_MANAGE) ? 'create' : 'suggest';
}

export interface VocabularyPickerProps {
  /** The list key, e.g. `tenant_tag` or `flag`. */
  list: string;
  tier: 'tenant' | 'library';
  label: string;
  /** Selected keys, in the order they were picked. */
  value: readonly string[];
  onChange: (keys: string[]) => void;
  /** False when the host draws the selected values itself (a record's own tags). */
  showSelected?: boolean;
  /**
   * False when the caller may not put an existing value on the record: the
   * matches are listed so the value is seen to exist, but none can be chosen,
   * and only the last option (Suggest) acts.
   */
  canPick?: boolean;
}

export function VocabularyPicker({ list, tier, label, value, onChange, showSelected = true, canPick = true }: VocabularyPickerProps) {
  const t = useT();
  const id = useId();
  const permissions = usePermissions();
  const values = useVocabularyValues(list);
  const create = useCreateValue(list);
  // One route for both: a suggestion on a tenant list, a proposal on a library list.
  const suggest = useSuggestValue(list);

  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [expanded, setExpanded] = useState<'create' | 'suggest' | null>(null);
  const [draftLabel, setDraftLabel] = useState('');
  const [usageNote, setUsageNote] = useState('');
  const [proposed, setProposed] = useState<string | null>(null);
  const [suggested, setSuggested] = useState<string | null>(null);

  const rows = values.data ?? [];
  const byKey = new Map(rows.map((row) => [row.key, row]));
  const available = rows.filter((row) => !value.includes(row.key));
  const { exact, matches } = nearMatches(query, available);
  const last = query.trim() === '' || exact !== null ? null : lastOption(tier, permissions);
  const optionCount = matches.length + (last === null ? 0 : 1);
  const listboxId = `${id}-listbox`;
  const inputId = `${id}-input`;
  const write = expanded === 'suggest' ? suggest : create;
  // The refusal's code decides the words; either way the value already there is offered.
  const exactRefusal = exactDuplicateFrom(write.error)?.[0];
  const refused = exactRefusal ?? nearDuplicateFrom(write.error)?.[0];

  const reset = () => {
    setQuery('');
    setOpen(false);
    setActive(0);
    setExpanded(null);
    setDraftLabel('');
    setUsageNote('');
    create.reset();
    suggest.reset();
  };

  const pick = (row: Pick<VocabularyRow, 'key'>) => {
    onChange([...value, row.key]);
    reset();
  };

  const choose = (index: number) => {
    const row = matches[index];
    if (row !== undefined) {
      if (canPick) pick(row);
      return;
    }
    if (last === 'create' || last === 'suggest') {
      setDraftLabel(query.trim());
      setExpanded(last);
      setOpen(false);
    }
    if (last === 'propose') {
      suggest.mutate(
        { labels: { en: query.trim() } },
        {
          onSuccess: (result) => {
            if (result.outcome === 'proposed') setProposed(result.proposal.title.length > 0 ? result.proposal.title : query.trim());
            reset();
          },
        },
      );
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(optionCount - 1, i + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (event.key === 'Enter' && open && optionCount > 0) {
      event.preventDefault();
      choose(active);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  const submit = () => {
    const label = draftLabel.trim();
    if (label === '') return;
    const body = { labels: { en: label }, usageNote: usageNote.trim() };
    if (expanded === 'suggest') {
      suggest.mutate(body, {
        onSuccess: () => {
          setSuggested(label);
          reset();
        },
      });
      return;
    }
    create.mutate(body, {
      onSuccess: (result) => {
        if (result.outcome === 'applied') pick(result.result);
      },
    });
  };

  return (
    <div className="mb-3.5 grid gap-1.5" data-vocabulary-picker={list}>
      <label htmlFor={inputId} className="font-semibold text-meta">
        {label}
      </label>

      {showSelected && value.length > 0 ? (
        <ul className="m-0 flex list-none flex-wrap items-center gap-1.5 p-0" data-picker-selected="">
          {value.map((key) => {
            const row = byKey.get(key);
            const pill = presentVocabularyValue(list, { key, kind: row?.kind ?? null, label: row?.label ?? key, extra: row?.extra ?? {} });
            return (
              <li key={key} className="inline-flex items-center gap-0.5">
                <Pill tone={pill.tone} outlined={pill.outlined}>
                  {pill.label}
                </Pill>
                <button type="button" className="rounded-full px-1 text-muted hover:text-fg" aria-label={t('picker.remove', { label: pill.label })} onClick={() => onChange(value.filter((k) => k !== key))}>
                  {REMOVE_GLYPH}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {values.isError ? (
        <div role="alert" className="flex flex-wrap items-center gap-2">
          <span className="text-meta text-negative">{t('picker.error')}</span>
          <Button variant="outline" size="small" onClick={() => void values.refetch()}>
            {t('common.tryAgain')}
          </Button>
        </div>
      ) : (
        <div className="relative">
          <input
            id={inputId}
            role="combobox"
            aria-expanded={open}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={open && optionCount > 0 ? `${id}-option-${active}` : undefined}
            autoComplete="off"
            className={controlClass}
            disabled={values.isPending}
            placeholder={values.isPending ? t('picker.loading') : t('picker.placeholder')}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
              setActive(0);
              setProposed(null);
              setSuggested(null);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
          />
          {open && query.trim() !== '' ? (
            <ul id={listboxId} role="listbox" aria-label={t('picker.options')} className="absolute z-20 mt-1 grid w-full list-none gap-0 rounded-card border border-line bg-surface p-1 shadow-lg">
              {matches.map((row, index) => (
                <li
                  key={row.key}
                  id={`${id}-option-${index}`}
                  role="option"
                  aria-selected={index === active}
                  aria-disabled={canPick ? undefined : true}
                  className={cn('rounded-control px-2 py-1.5', canPick && 'cursor-pointer', index === active && 'bg-neutral-soft')}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(index)}
                  data-picker-option={row.key}
                >
                  <Pill {...toneOf(list, row)}>{row.label}</Pill>
                  {index === 0 && exact === null ? <small className="ml-2 text-meta text-muted">{t('picker.didYouMean', { usage: usageText(row.usageCount, t) })}</small> : null}
                </li>
              ))}
              {matches.length === 0 ? <li className="px-2.5 py-2 text-muted">{t('picker.noMatch')}</li> : null}
              {last !== null ? (
                <li
                  id={`${id}-option-${matches.length}`}
                  role="option"
                  aria-selected={active === matches.length}
                  className={cn('cursor-pointer rounded-control px-2 py-1.5', active === matches.length && 'bg-neutral-soft')}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(matches.length)}
                  data-picker-last={last}
                >
                  <span className="font-semibold">{t(LAST_TITLE[last], { label: query.trim() })}</span>
                  <small className="block text-meta text-muted">{last === 'create' ? t('picker.createHint', { list: listLabel(list, t) }) : t(LAST_HINT[last])}</small>
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      )}

      {expanded !== null ? (
        <div className="rounded-card border border-line bg-surface p-4" data-picker-create="">
          <Field id={`${id}-create-label`} label={t('admin.vocabularies.label')}>
            <TextInput id={`${id}-create-label`} value={draftLabel} autoFocus onChange={(e) => setDraftLabel(e.target.value)} />
          </Field>
          <Field id={`${id}-create-note`} label={t('admin.vocabularies.usageNote')} hint={t('admin.vocabularies.usageNoteHint')}>
            <TextArea id={`${id}-create-note`} placeholder={t('admin.vocabularies.usageNotePlaceholder')} value={usageNote} onChange={(e) => setUsageNote(e.target.value)} />
          </Field>
          {refused !== undefined ? (
            <div role="alert" className="flex flex-wrap items-center gap-2" data-near-duplicate="">
              <span className="text-meta text-negative">{exactRefusal !== undefined ? t('picker.alreadyExists', { label: refused.label }) : t('admin.vocabularies.didYouMean', { label: refused.label })}</span>
              <Button variant="outline" size="small" onClick={() => pick(refused)}>
                {t('picker.useExisting', { label: refused.label })}
              </Button>
            </div>
          ) : write.isError ? (
            <ProblemAlert error={write.error} />
          ) : null}
          <ButtonBar>
            <Button variant="outline" size="small" onClick={reset} disabled={write.isPending}>
              {t('common.cancel')}
            </Button>
            <Button size="small" onClick={submit} disabled={write.isPending || draftLabel.trim() === ''}>
              {expanded === 'suggest' ? t('picker.sendSuggestion') : t('picker.createAndSelect')}
            </Button>
          </ButtonBar>
        </div>
      ) : null}

      {expanded === null && suggest.isError ? <ProblemAlert error={suggest.error} /> : null}
      {proposed !== null ? <StatusLine tone="positive">{t('admin.vocabularies.proposed', { title: proposed })}</StatusLine> : null}
      {suggested !== null ? (
        <div role="status" className="grid gap-1" data-picker-suggested="">
          <PillRow pills={presentSuggestedValue(suggested, t)} />
          <small className="text-meta text-muted">{t('picker.suggestedNote')}</small>
        </div>
      ) : null}
    </div>
  );
}

const LAST_TITLE = { create: 'picker.create', suggest: 'picker.suggest', propose: 'picker.propose' } as const;
const LAST_HINT = { suggest: 'picker.suggestHint', propose: 'picker.proposeHint' } as const;

/** The remove affordance's glyph: an icon, not copy; its name comes from the catalog. */
const REMOVE_GLYPH = '×';

function toneOf(list: string, row: VocabularyRow) {
  const pill = presentVocabularyValue(list, row);
  return { tone: pill.tone, outlined: pill.outlined };
}
