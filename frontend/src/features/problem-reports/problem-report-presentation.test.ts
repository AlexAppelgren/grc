import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { CLOSING_STATUSES, canClose, contextLine, presentProblemReport, statusLabel, statusTone } from './problem-report-presentation';
import type { ProblemReport } from './types';

// A report's pill reads its status kind; who may close it reads the reporter's
// id and the reader's permissions, never a role name.

const t = createT('en');
const sv = createT('sv');
const names = (code: string) => ({ sv: 'Swedish', en: 'English' })[code] ?? code;

const open = { status: 'open', reporter: { id: 'u-reader', name: 'Johan Berg' } } as const satisfies Pick<ProblemReport, 'status' | 'reporter'>;

describe('the status pill', () => {
  it('gives each status its label and its tone by kind', () => {
    expect(presentProblemReport({ status: 'open' }, t)).toEqual([{ key: 'status', label: 'Open', tone: 'warning', order: 0 }]);
    expect([statusLabel('answered', t), statusTone('answered')]).toEqual(['Answered', 'information']);
    expect([statusLabel('fixed', t), statusTone('fixed')]).toEqual(['Fixed', 'positive']);
    expect([statusLabel('rejected', t), statusTone('rejected')]).toEqual(['Rejected', 'information']);
    expect(statusLabel('fixed', sv)).toBe('Åtgärdad');
  });

  it('falls back for a status the catalog does not know, rather than throwing', () => {
    expect(statusLabel('reopened', t)).toBe('Other');
    expect(statusTone('reopened')).toBe('information');
  });

  it('offers the three closing states and never open', () => {
    expect(CLOSING_STATUSES).toEqual(['answered', 'fixed', 'rejected']);
  });
});

describe('who may close', () => {
  it('lets a holder of proposals.create close any open report of the bank', () => {
    expect(canClose(open, 'u-officer', ['problems.report', 'proposals.create'])).toBe(true);
  });

  it('lets the reporter close their own, and nobody else without the permission', () => {
    expect(canClose(open, 'u-reader', ['problems.report'])).toBe(true);
    expect(canClose(open, 'u-other', ['problems.report'])).toBe(false);
    expect(canClose(open, null, ['problems.report'])).toBe(false);
  });

  it('offers no close on a report that is closed already', () => {
    for (const status of CLOSING_STATUSES) {
      expect(canClose({ ...open, status }, 'u-reader', ['problems.report', 'proposals.create'])).toBe(false);
    }
  });
});

describe('what the reporter had on screen', () => {
  it('names the version and the language when both were recorded, either alone, or neither', () => {
    expect(contextLine({ versionNumber: 2, language: 'sv' }, names, t)).toBe('Version 2, Swedish');
    expect(contextLine({ versionNumber: null, language: 'en' }, names, t)).toBe('English');
    expect(contextLine({ versionNumber: 1, language: null }, names, t)).toBe('Version 1');
    expect(contextLine({ versionNumber: null, language: null }, names, t)).toBeNull();
  });
});
