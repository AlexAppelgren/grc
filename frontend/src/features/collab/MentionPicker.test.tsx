import { fireEvent, render, screen } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { MentionPicker, mentionQuery } from './MentionPicker';
import type { PersonRef } from './types';

// The mention control: "@" opens the bank's people from GET /reference/people,
// filtered by the letters after it; arrows move, Enter or a click chooses,
// Escape closes; the chosen person is written as their name and handed back.

const PEOPLE = [
  { id: 'u-1', name: 'Anna Ek' },
  { id: 'u-2', name: 'Johan Berg' },
  { id: 'u-3', name: 'Jonas Holm' },
];

function Harness({ picked }: { picked: PersonRef[] }) {
  const [value, setValue] = useState('');
  return <MentionPicker id="m" aria-label="Text" value={value} onValueChange={setValue} onPick={(p) => picked.push(p)} />;
}

function renderPicker(picked: PersonRef[] = []): Sent[] {
  const sent = installAdapter(() => ({ status: 200, data: PEOPLE }));
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  render(
    <Wrapper>
      <LocaleProvider locale="en">
        <Harness picked={picked} />
      </LocaleProvider>
    </Wrapper>,
  );
  return sent;
}

const type = (value: string) => fireEvent.change(screen.getByRole('combobox'), { target: { value, selectionStart: value.length } });

describe('mentionQuery', () => {
  it('reads the letters after an "@" the caret sits in, and nothing else', () => {
    expect(mentionQuery('@', 1)).toBe('');
    expect(mentionQuery('Hi @jo', 6)).toBe('jo');
    expect(mentionQuery('Hi @jo there', 12)).toBeNull();
    expect(mentionQuery('mail@example', 12)).toBeNull();
    expect(mentionQuery('Hi @jo', 3)).toBeNull();
  });
});

describe('MentionPicker', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('asks for the people only once someone types "@"', async () => {
    const sent = renderPicker();
    type('Hello');
    expect(sent).toEqual([]);
    type('Hello @');
    expect(await screen.findAllByRole('option')).toHaveLength(3);
    expect(sent.map((s) => s.path)).toEqual(['/api/v1/reference/people']);
  });

  it('moves with the arrows and chooses with Enter', async () => {
    const picked: PersonRef[] = [];
    renderPicker(picked);
    type('Ask @jo');
    await screen.findByRole('option', { name: 'Johan Berg' });
    const box = screen.getByRole('combobox');
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: 'Jonas Holm' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: 'Johan Berg' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(box).toHaveValue('Ask Jonas Holm ');
    expect(picked).toEqual([PEOPLE[2]]);
  });

  it('chooses with a click, and closes on Escape and when the text loses focus', async () => {
    const picked: PersonRef[] = [];
    renderPicker(picked);
    type('@an');
    fireEvent.click(await screen.findByRole('option', { name: 'Anna Ek' }));
    expect(screen.getByRole('combobox')).toHaveValue('Anna Ek ');
    expect(picked).toEqual([PEOPLE[0]]);

    type('Anna Ek @');
    await screen.findAllByRole('option');
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();

    type('Anna Ek @j');
    await screen.findAllByRole('option');
    fireEvent.blur(screen.getByRole('combobox'));
    expect(screen.queryByRole('listbox')).toBeNull();
  });
});
