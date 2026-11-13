import { describe, expect, it } from 'vitest';

import type { RegisterEntityStatus, RegisterEntry } from '@/features/register/types';

import { answersOf } from './ObligationApplicabilityPanel';

// Which answers "Does it apply" shows (REG-01, D-42): per legal entity where the
// obligation spans several, else the whole obligation's. The dialog that sets
// one is exercised where it opens, in ObligationPositionPanel.test.tsx.

const SARA = { id: 'u1', name: 'Sara Lindqvist' };
const NOT_ASSESSED = { key: 'not_assessed', kind: 'not_assessed', label: 'Not assessed' };

function entity(id: string, name: string, patch: Partial<RegisterEntityStatus> = {}): RegisterEntityStatus {
  return {
    orgUnitId: id,
    orgUnitName: name,
    applicability: 'applies',
    applicabilityReason: 'We give advice and manage portfolios.',
    applicabilityDecidedAt: '2026-09-18T08:30:00Z',
    applicabilityDecidedBy: SARA,
    complianceStatus: NOT_ASSESSED,
    statusNote: null,
    riskRating: null,
    owner: null,
    ownerTeam: null,
    process: null,
    system: null,
    evidenceLocation: null,
    nextReviewDate: null,
    version: 2,
    ...patch,
  };
}

function entry(patch: Partial<RegisterEntry> = {}): RegisterEntry {
  return {
    obligationId: 'ob-1',
    interpretation: { obligationId: 'ob-1', current: null, earlier: [] },
    applicability: 'under_assessment',
    applicabilityReason: null,
    applicabilityDecidedAt: null,
    applicabilityDecidedBy: null,
    complianceStatus: NOT_ASSESSED,
    statusNote: null,
    riskRating: null,
    firstLineOwner: null,
    complianceContact: null,
    ownerTeam: null,
    process: null,
    system: null,
    evidenceLocation: null,
    nextReviewDate: null,
    entities: [],
    version: 0,
    updatedAt: null,
    ...patch,
  };
}

const SPAN = [
  { orgUnitId: 'e-bank', orgUnitName: 'Example Bank AB' },
  { orgUnitId: 'e-liv', orgUnitName: 'Example Liv AB' },
];

describe('answersOf', () => {
  it('answers for the obligation as a whole where it spans one entity or none', () => {
    expect(answersOf(entry(), [SPAN[0]!]).map((answer) => answer.orgUnitId)).toEqual([null]);
    expect(answersOf(entry(), []).map((answer) => answer.orgUnitId)).toEqual([null]);
  });

  it('answers per entity where it spans several, an unanswered one at version 0, and keeps a whole answer someone gave', () => {
    const bank = entity('e-bank', 'Example Bank AB', { version: 3 });
    expect(answersOf(entry({ entities: [bank] }), SPAN).map((answer) => [answer.orgUnitId, answer.applicability, answer.version])).toEqual([
      ['e-bank', 'applies', 3],
      ['e-liv', 'under_assessment', 0],
    ]);
    const decided = entry({ applicability: 'applies', applicabilityReason: 'Both entities advise.', version: 4 });
    expect(answersOf(decided, SPAN).map((answer) => answer.orgUnitId)).toEqual([null, 'e-bank', 'e-liv']);
  });

  it('keeps an answered entity the obligation no longer spans, after the spanned ones', () => {
    const fonder = entity('e-fonder', 'Example Fonder AB');
    expect(answersOf(entry({ entities: [fonder] }), SPAN).map((answer) => answer.name)).toEqual(['Example Bank AB', 'Example Liv AB', 'Example Fonder AB']);
  });
});
