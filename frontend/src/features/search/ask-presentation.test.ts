import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import { aiBasisLabel, citationLabel, isCutShort, presentStatement } from './ask-presentation';
import type { AnswerStatement } from './types';

// Pins what an answer's statement, citation and label read as
// (design/screens/tenant-ask.html, design/system/pills-and-labels.md).

const t = createT('en');
const ctx = defaultFormatContext;

function statement(overrides: Partial<AnswerStatement> = {}): AnswerStatement {
  return { text: 'Costs are disclosed.', citationIndexes: [1], ...overrides };
}

describe('presentStatement', () => {
  it('carries no pill when no change is pending on what the statement cites', () => {
    expect(presentStatement(statement(), t, ctx)).toEqual([]);
  });

  it('flags a pending change as the warning pill "Change pending", dated to its precision', () => {
    const day = presentStatement(statement({ pendingChangeId: 'chg-1', pendingChangeInForceOn: '2026-10-01', pendingChangeInForceOnPrecision: 'day' }), t, ctx);
    expect(day).toEqual([{ key: 'change-pending', label: 'Change pending: 1 Oct 2026', tone: 'warning', order: 0 }]);

    const month = presentStatement(statement({ pendingChangeId: 'chg-1', pendingChangeInForceOn: '2027-01-01', pendingChangeInForceOnPrecision: 'month' }), t, ctx);
    expect(month[0]?.label).toBe('Change pending: January 2027');
  });
});

describe('citationLabel', () => {
  it('reads as a lawyer would cite it, with the version read', () => {
    expect(citationLabel({ index: 1, obligationId: 'ob-1', versionNo: 2, instrumentShortName: 'FFFS 2017:2', refLabel: '9 kap. 6 §' }, t)).toBe('FFFS 2017:2, 9 kap. 6 §, version 2');
  });
});

describe('aiBasisLabel', () => {
  it('names what the answer is drafted from and the date it was read at', () => {
    expect(aiBasisLabel('2026-06-01', t, ctx)).toBe('Answer drafted by AI from inventory records only, as of 1 Jun 2026');
  });
});

describe('isCutShort', () => {
  it('is true only for an answer the model stopped at its length limit', () => {
    expect(isCutShort('max_tokens')).toBe(true);
    expect(isCutShort('end_turn')).toBe(false);
    expect(isCutShort(null)).toBe(false);
  });
});
