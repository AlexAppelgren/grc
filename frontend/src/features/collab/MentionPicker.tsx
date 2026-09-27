'use client';

import { useQuery } from '@tanstack/react-query';
import { useRef, useState, type KeyboardEvent, type TextareaHTMLAttributes } from 'react';

import { controlClass } from '@/components/ui/Field';
import { useT } from '@/shared/i18n/LocaleProvider';
import { api } from '@/shared/utils/api-client';
import { cn } from '@/shared/utils/cn';

import type { PersonRef } from './types';

// The composer's textarea with its mention list (COL-01,
// design/system/comments-and-mentions.md "Mentions"). Typing "@" opens the
// bank's people from GET /reference/people, filtered by the letters typed
// after it; choosing one writes the name into the text and hands the person
// to the composer, which sends their id beside the body. The text is never
// parsed for ids.

const PEOPLE_SHOWN = 8;

async function listPeople(): Promise<PersonRef[]> {
  return (await api.get<PersonRef[]>('/api/v1/reference/people')).data;
}

// "@" at the start or after a space, then the letters typed so far, up to the caret.
const TRIGGER = /(?:^|\s)@([^\s@]*)$/;

/** The letters after an "@" the caret sits in, or null when it sits in none. */
export function mentionQuery(text: string, caret: number): string | null {
  return TRIGGER.exec(text.slice(0, caret))?.[1] ?? null;
}

export function MentionPicker({
  id,
  value,
  onValueChange,
  onPick,
  ...rest
}: {
  id: string;
  value: string;
  onValueChange: (value: string) => void;
  onPick: (person: PersonRef) => void;
} & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id' | 'value' | 'onChange'>) {
  const t = useT();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const people = useQuery({ queryKey: ['collab', 'people'], queryFn: listPeople, enabled: query !== null, staleTime: 60_000 });

  const letters = query?.toLocaleLowerCase() ?? '';
  const matches = (people.data ?? []).filter((p) => p.name.toLocaleLowerCase().includes(letters)).slice(0, PEOPLE_SHOWN);
  const open = query !== null && people.isSuccess;
  const current = matches.at(Math.min(active, matches.length - 1));
  const listboxId = `${id}-people`;

  function track(text: string, caret: number) {
    setQuery(mentionQuery(text, caret));
    setActive(0);
  }

  function choose(person: PersonRef) {
    const area = ref.current;
    const caret = area?.selectionStart ?? value.length;
    const start = caret - (query?.length ?? 0) - 1;
    const next = `${value.slice(0, start)}${person.name} ${value.slice(caret)}`;
    onValueChange(next);
    onPick(person);
    setQuery(null);
    const at = start + person.name.length + 1;
    requestAnimationFrame(() => {
      area?.focus();
      area?.setSelectionRange(at, at);
    });
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      setQuery(null);
    } else if (matches.length > 0 && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      setActive((i) => (i + (e.key === 'ArrowDown' ? 1 : matches.length - 1)) % matches.length);
    } else if (e.key === 'Enter' && current !== undefined) {
      e.preventDefault();
      choose(current);
    }
  }

  return (
    <div className="relative">
      <textarea
        {...rest}
        className={cn(controlClass, 'field-sizing-content h-auto min-h-[76px] resize-y py-2')}
        ref={ref}
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={open && current !== undefined ? `${listboxId}-${current.id}` : undefined}
        value={value}
        onChange={(e) => {
          onValueChange(e.target.value);
          track(e.target.value, e.target.selectionStart);
        }}
        onSelect={(e) => track(e.currentTarget.value, e.currentTarget.selectionStart)}
        onBlur={() => setQuery(null)}
        onKeyDown={onKeyDown}
      />
      {open ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={t('collab.mentions.options')}
          className="absolute z-20 mt-1 grid w-full list-none gap-0 rounded-card border border-line bg-surface p-1 shadow-lg"
          data-mention-list=""
        >
          {matches.map((person, index) => (
            <li
              key={person.id}
              id={`${listboxId}-${person.id}`}
              role="option"
              aria-selected={index === active}
              className={cn('cursor-pointer rounded-control px-2 py-1.5 font-medium', index === active && 'bg-neutral-soft')}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(person)}
            >
              {person.name}
            </li>
          ))}
          {matches.length === 0 ? <li className="px-2.5 py-2 text-muted">{t('collab.comments.noMatch', { letters: query })}</li> : null}
        </ul>
      ) : null}
    </div>
  );
}
