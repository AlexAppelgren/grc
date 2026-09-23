import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import { confirmedLine, inForceLine, KIND_FILTER, outsideScopeLine, presentLibraryUpdate, titleOf, updateKindLabel } from './library-updates-presentation';
import type { LibraryUpdateRow } from './types';

const t = createT('en');
const sv = createT('sv');
const ctx = defaultFormatContext;

// The generated contract's own example row (LibraryUpdateRow in openapi.json).
const TARGET = {
  id: '3c1f8a52-62d4-4a1b-8a0e-0f9d7e5b2a44',
  title: 'Pay for third-party research only under the permitted models',
  referenceLabel: 'Third-party payments',
  instrumentShortName: 'FFFS 2017:2',
};

// Who stood behind the change: a person approved it, and no agent proposed or confirmed
// it. Spread in, so the row holds these fields whether or not the contract it is typed
// by names them yet.
const APPROVED_BY_A_PERSON = { verifiedOrigin: 'user', proposedByAgent: null, confirmedByAgent: null };

function row(overrides: Partial<LibraryUpdateRow> = {}): LibraryUpdateRow {
  return {
    ...APPROVED_BY_A_PERSON,
    id: '8f1d6d9e-58f0-4c2e-9e2f-6a4a6f1b8c21',
    kind: 'new_obligation_version',
    appliedAt: '2026-09-18T09:20:00Z',
    effectiveFrom: { date: '2026-10-01', precision: 'day' },
    target: TARGET,
    versionNumber: 2,
    vocabulary: null,
    vocabularyList: null,
    inFootprint: true,
    outsideReason: [],
    ...overrides,
  };
}

const flagRenamed = row({
  kind: 'vocabulary_relabel',
  effectiveFrom: null,
  target: null,
  versionNumber: null,
  vocabulary: { key: 'advice_perimeter', kind: null, label: 'Advice perimeter (RIS)' },
  vocabularyList: 'flag',
});

describe('updateKindLabel', () => {
  it('reads every vocabulary and term kind as "Vocabulary"', () => {
    expect(updateKindLabel('new_obligation_version', t)).toBe('New version');
    for (const kind of KIND_FILTER.vocabulary.split(',')) {
      expect(updateKindLabel(kind, t)).toBe('Vocabulary');
    }
  });

  it('names each kind of new record by its own label, in both languages', () => {
    expect(['new_instrument', 'new_obligation', 'new_provision', 'new_provision_version'].map((kind) => updateKindLabel(kind, t))).toEqual([
      'New instrument',
      'New obligation',
      'New provision',
      'New provision version',
    ]);
    expect(updateKindLabel('new_obligation', sv)).toBe('Ny skyldighet');
  });

  it('falls back for an unknown kind rather than throwing', () => {
    expect(updateKindLabel('something_new', t)).toBe('Update');
  });
});

describe('KIND_FILTER', () => {
  it('asks for every vocabulary and term kind at once, as the route takes them', () => {
    expect(KIND_FILTER.vocabulary.split(',')).toEqual([
      'vocabulary_create',
      'vocabulary_relabel',
      'vocabulary_retire',
      'vocabulary_restore',
      'vocabulary_merge',
      'term_create',
      'term_update',
    ]);
    expect(KIND_FILTER.newVersion).toBe('new_obligation_version');
  });
});

describe('presentLibraryUpdate', () => {
  it('shows the instrument pill for an obligation update', () => {
    const pills = presentLibraryUpdate(row(), t);
    expect(pills.map((p) => p.key)).toEqual(['kind', 'instrument']);
    expect(pills[0]).toMatchObject({ label: 'New version', tone: 'notice' });
    expect(pills[1]).toMatchObject({ label: 'FFFS 2017:2', tone: 'brand' });
  });

  it('names the changed row by its label for a vocabulary update, never by the list key', () => {
    const pills = presentLibraryUpdate(flagRenamed, t);
    expect(pills.map((p) => p.key)).toEqual(['kind', 'vocabulary']);
    expect(pills[1]).toMatchObject({ label: 'Advice perimeter (RIS)', tone: 'brand' });
    expect(pills.map((p) => p.label)).not.toContain('flag');
  });

  it('shows only the kind pill when the changed row has since been deleted', () => {
    expect(presentLibraryUpdate({ ...flagRenamed, vocabulary: null }, t).map((p) => p.key)).toEqual(['kind']);
    expect(presentLibraryUpdate({ ...flagRenamed, vocabulary: undefined }, t).map((p) => p.key)).toEqual(['kind']);
  });

  it('shows only the kind pill when the instrument has no short name', () => {
    expect(presentLibraryUpdate(row({ target: { ...TARGET, instrumentShortName: '' } }), t).map((p) => p.key)).toEqual(['kind']);
  });
});

describe('titleOf', () => {
  it("is the library record's own title for an obligation update", () => {
    expect(titleOf(row(), t)).toBe('Pay for third-party research only under the permitted models');
  });

  it('falls back to the reference when the record has no title in any language', () => {
    expect(titleOf(row({ target: { ...TARGET, title: '' } }), t)).toBe('Third-party payments');
  });

  it('falls back to the kind label for a vocabulary update, which names no record of its own', () => {
    expect(titleOf(flagRenamed, t)).toBe('Vocabulary');
    expect(titleOf({ ...flagRenamed, target: undefined }, t)).toBe('Vocabulary');
  });
});

describe('inForceLine', () => {
  it('renders the legal date at the precision it is known to', () => {
    expect(inForceLine(row(), t, ctx)).toBe('In force from 1 Oct 2026');
    expect(inForceLine(row({ effectiveFrom: { date: '2026-10-01', precision: 'quarter' } }), t, ctx)).toBe('In force from Q4 2026');
    expect(inForceLine(row({ effectiveFrom: { date: '2026-10-01', precision: 'month' } }), t, ctx)).toBe('In force from October 2026');
    expect(inForceLine(row({ effectiveFrom: { date: '2027-01-01', precision: 'year' } }), t, ctx)).toBe('In force from 2027');
  });

  it('says nothing when the change carries no legal date', () => {
    expect(inForceLine(flagRenamed, t, ctx)).toBeNull();
    expect(inForceLine(row({ effectiveFrom: undefined }), t, ctx)).toBeNull();
  });
});

describe('outsideScopeLine', () => {
  const outside = row({
    inFootprint: false,
    outsideReason: [
      {
        dimension: { key: 'service_type', kind: null, label: 'Service' },
        terms: [
          { key: 'execution_only', kind: null, label: 'Execution only' },
          { key: 'custody', kind: null, label: 'Custody' },
        ],
      },
      { dimension: { key: 'legal_entity', kind: null, label: 'Legal entity' }, terms: [{ key: 'insurer', kind: null, label: 'Insurer' }] },
    ],
  });

  it('names every term that puts the duty outside, by label, across every facet', () => {
    expect(outsideScopeLine(outside, t)).toBe('Outside our scope: Execution only, Custody, Insurer');
    expect(outsideScopeLine(outside, sv)).toBe('Utanför vår omfattning: Execution only, Custody, Insurer');
  });

  it('says nothing on a row inside the footprint', () => {
    expect(outsideScopeLine(row(), t)).toBeNull();
    expect(outsideScopeLine({ inFootprint: true, outsideReason: undefined }, t)).toBeNull();
  });
});

describe('confirmedLine', () => {
  const byAgents = { verifiedOrigin: 'agent', proposedByAgent: { id: 'ag-1', key: 'watch-sweeper' }, confirmedByAgent: { id: 'ag-2', key: 'library-confirmer' } };

  it('names both agents when an independent agent confirmed what another agent proposed', () => {
    expect(confirmedLine(row(byAgents), t)).toBe('Machine-confirmed: proposed by watch-sweeper, confirmed by library-confirmer');
    expect(confirmedLine(row(byAgents), sv)).toBe('Maskinbekräftad: föreslagen av watch-sweeper, bekräftad av library-confirmer');
  });

  it('names the confirming agent alone when no agent proposed it, and decides by who confirmed, never by which agents are named', () => {
    expect(confirmedLine(row({ ...byAgents, proposedByAgent: null }), t)).toBe('Machine-confirmed by library-confirmer');
    // A person approved an agent's proposal: that is a person's approval, and the row says nothing.
    expect(confirmedLine(row({ ...byAgents, verifiedOrigin: 'user', confirmedByAgent: null }), t)).toBeNull();
    expect(confirmedLine(row(), t)).toBeNull();
  });
});
