'use client';

import { useId, useState, type KeyboardEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextArea, TextInput, controlClass } from '@/components/ui/Field';
import { Pill } from '@/components/ui/Pill';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useCreateValue, useSuggestValue, useVocabularyValues } from '@/features/vocabularies/hooks';
import type { VocabularyRow } from '@/features/vocabularies/types';
import { exactDuplicateFrom, listLabel, nearDuplicateFrom, nearMatches, presentVocabularyValue, usageText } from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';

// The one picker for every vocabulary (design/screens/picker-create-or-suggest.html).
// The combobox lists existing values, offers the near match before anything
// else, then one last option by the list's tier:
//
//   - a TENANT list, for a holder of `vocab.manage`: Create, expanded in place
//     for the usage note (VOC-01). The server's near_duplicate refusal renders
//     in place with the match as a button (AC-VOC3).
//   - a LIBRARY list, for a holder of `proposals.create`: Propose, which
//     becomes a proposal the platform console reviews (VOC-07). The value is
//     used once approved.
//
// A tenant list for someone WITHOUT `vocab.manage` gets no last option. The
// card's "Suggest" for that case is VOC-03 ("create where you use it"), which
// is R2: when it lands, it is the third branch of `lastOption` below.

const VOCAB_MANAGE = 'vocab.manage';
const PROPOSALS_CREATE = 'proposals.create';

type LastOption = 'create' | 'propose' | null;

export function lastOption(tier: 'tenant' | 'library', permissions: readonly string[]): LastOption {
  if (tier === 'library') return permissions.includes(PROPOSALS_CREATE) ? 'propose' : null;
  return permissions.includes(VOCAB_MANAGE) ? 'create' : null;
}

export interface VocabularyPickerProps {
  /** The list key, e.g. `tenant_tag` or `flag`. */
  list: string;
  tier: 'tenant' | 'library';
  label: string;
  /** Selected keys, in the order they were picked. */
  value: readonly string[];
  onChange: (keys: string[]) => void;
}

export function VocabularyPicker({ list, tier, label, value, onChange }: VocabularyPickerProps) {
  const t = useT();
  const id = useId();
  const permissions = usePermissions() ?? [];
  const values = useVocabularyValues(list);
  const create = useCreateValue(list);
  const propose = useSuggestValue(list);

  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [draftLabel, setDraftLabel] = useState('');
  const [usageNote, setUsageNote] = useState('');
  const [proposed, setProposed] = useState<string | null>(null);

  const rows = values.data ?? [];
  const byKey = new Map(rows.map((row) => [row.key, row]));
  const available = rows.filter((row) => !value.includes(row.key));
  const { exact, matches } = nearMatches(query, available);
  const last = query.trim() === '' || exact !== null ? null : lastOption(tier, permissions);
  const optionCount = matches.length + (last === null ? 0 : 1);
  const listboxId = `${id}-listbox`;
  const inputId = `${id}-input`;
  const refused = nearDuplicateFrom(create.error) ?? exactDuplicateFrom(create.error);

  const reset = () => {
    setQuery('');
    setOpen(false);
    setActive(0);
    setExpanded(false);
    setDraftLabel('');
    setUsageNote('');
    create.reset();
  };

  const pick = (row: Pick<VocabularyRow, 'key'>) => {
    onChange([...value, row.key]);
    reset();
  };

  const choose = (index: number) => {
    const row = matches[index];
    if (row !== undefined) {
      pick(row);
      return;
    }
    if (last === 'create') {
      setDraftLabel(query.trim());
      setExpanded(true);
      setOpen(false);
    }
    if (last === 'propose') {
      propose.mutate(
        { labels: { en: query.trim() } },
        {
          onSuccess: (proposal) => {
            setProposed(proposal.title.length > 0 ? proposal.title : query.trim());
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

  const submitCreate = () => {
    if (draftLabel.trim() === '') return;
    create.mutate(
      { labels: { en: draftLabel.trim() }, usageNote: usageNote.trim() },
      {
        onSuccess: (write) => {
          if (write.outcome === 'applied') pick(write.result);
        },
      },
    );
  };

  return (
    <div className="mb-3.5 grid gap-1.5" data-vocabulary-picker={list}>
      <label htmlFor={inputId} className="font-semibold text-meta">
        {label}
      </label>

      {value.length > 0 ? (
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
                  className={cn('cursor-pointer rounded-control px-2 py-1.5', index === active && 'bg-neutral-soft')}
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
                  <span className="font-semibold">{last === 'create' ? t('picker.create', { label: query.trim() }) : t('picker.propose', { label: query.trim() })}</span>
                  <small className="block text-meta text-muted">{last === 'create' ? t('picker.createHint', { list: listLabel(list, t) }) : t('picker.proposeHint')}</small>
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      )}

      {expanded ? (
        <div className="rounded-card border border-line bg-surface p-4" data-picker-create="">
          <Field id={`${id}-create-label`} label={t('admin.vocabularies.label')}>
            <TextInput id={`${id}-create-label`} value={draftLabel} autoFocus onChange={(e) => setDraftLabel(e.target.value)} />
          </Field>
          <Field id={`${id}-create-note`} label={t('admin.vocabularies.usageNote')} hint={t('admin.vocabularies.usageNoteHint')}>
            <TextArea id={`${id}-create-note`} placeholder={t('admin.vocabularies.usageNotePlaceholder')} value={usageNote} onChange={(e) => setUsageNote(e.target.value)} />
          </Field>
          {refused !== null && refused[0] !== undefined ? (
            <div role="alert" className="flex flex-wrap items-center gap-2" data-near-duplicate="">
              <span className="text-meta text-negative">{t('picker.alreadyExists', { label: refused[0].label })}</span>
              <Button variant="outline" size="small" onClick={() => pick(refused[0] as { key: string })}>
                {t('picker.useExisting', { label: refused[0].label })}
              </Button>
            </div>
          ) : create.isError ? (
            <ProblemAlert error={create.error} />
          ) : null}
          <ButtonBar>
            <Button variant="outline" size="small" onClick={reset} disabled={create.isPending}>
              {t('common.cancel')}
            </Button>
            <Button size="small" onClick={submitCreate} disabled={create.isPending || draftLabel.trim() === ''}>
              {t('picker.createAndSelect')}
            </Button>
          </ButtonBar>
        </div>
      ) : null}

      {propose.isError ? <ProblemAlert error={propose.error} /> : null}
      {proposed !== null ? <StatusLine tone="positive">{t('admin.vocabularies.proposed', { title: proposed })}</StatusLine> : null}
    </div>
  );
}

/** The remove affordance's glyph: an icon, not copy; its name comes from the catalog. */
const REMOVE_GLYPH = '×';

function toneOf(list: string, row: VocabularyRow) {
  const pill = presentVocabularyValue(list, row);
  return { tone: pill.tone, outlined: pill.outlined };
}
