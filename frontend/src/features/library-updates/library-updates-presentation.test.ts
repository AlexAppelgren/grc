import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { presentLibraryUpdate, titleOf, updateKindLabel } from './library-updates-presentation';
import type { LibraryUpdateRow } from './types';

const t = createT('en');

function row(overrides: Partial<LibraryUpdateRow> = {}): LibraryUpdateRow {
  return {
    id: 'p-1',
    kind: 'new_obligation_version',
    appliedAt: '2026-09-17T10:14:00Z',
    effectiveFrom: '2026-10-01',
    target: { id: 'obl-1', title: 'Pay for third-party research only under the permitted models', referenceLabel: 'FFFS 2017:2', instrumentShortName: 'FFFS 2017:2' },
    vocabularyList: null,
    inFootprint: true,
    outsideTerms: [],
    ...overrides,
  };
}

describe('updateKindLabel', () => {
  it('reads every vocabulary and term kind as "Vocabulary"', () => {
    expect(updateKindLabel('new_obligation_version', t)).toBe('New version');
    for (const kind of ['vocabulary_create', 'vocabulary_relabel', 'vocabulary_retire', 'vocabulary_restore', 'vocabulary_merge', 'term_create', 'term_update']) {
      expect(updateKindLabel(kind, t)).toBe('Vocabulary');
    }
  });

  it('falls back for an unknown kind rather than throwing', () => {
    expect(updateKindLabel('something_new', t)).not.toBe('');
  });
});

describe('presentLibraryUpdate', () => {
  it('shows the instrument pill for an obligation update', () => {
    const pills = presentLibraryUpdate(row(), t);
    expect(pills.map((p) => p.key)).toEqual(['kind', 'instrument']);
    expect(pills[1]).toMatchObject({ label: 'FFFS 2017:2', tone: 'brand' });
  });

  it('shows the vocabulary list pill for a vocabulary update', () => {
    const pills = presentLibraryUpdate(row({ target: null, vocabularyList: 'flag' }), t);
    expect(pills.map((p) => p.key)).toEqual(['kind', 'list']);
    expect(pills[1]).toMatchObject({ label: 'flag', tone: 'brand' });
  });

  it('shows only the kind pill when there is neither an instrument nor a vocabulary list to name', () => {
    const pills = presentLibraryUpdate(row({ target: { id: 'obl-1', title: 'x', referenceLabel: 'x', instrumentShortName: '' }, vocabularyList: null }), t);
    expect(pills.map((p) => p.key)).toEqual(['kind']);
  });
});

describe('titleOf', () => {
  it('is the library record\'s own title for an obligation update', () => {
    expect(titleOf(row(), t)).toBe('Pay for third-party research only under the permitted models');
  });

  it('falls back to the kind label for a vocabulary update, which names no record of its own', () => {
    expect(titleOf(row({ kind: 'vocabulary_create', target: null, vocabularyList: 'flag' }), t)).toBe('Vocabulary');
  });
});
