import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { basisOf, suggestReason, type Basis } from './suggestion';

// The reason the Decide dialog suggests: facts the bank already holds, in the reader's
// language, and never the conclusion.

const en = { t: createT('en'), ctx: { locale: 'en', timeZone: 'Europe/Stockholm' } as const };
const sv = { t: createT('sv'), ctx: { locale: 'sv', timeZone: 'Europe/Stockholm' } as const };

const funds: Basis = { term: 'Funds', lines: ['Tillstånd att driva fondverksamhet'] };
const aml: Basis = { term: 'Anti-money laundering', lines: [] };
const read = { authority: 'Finansinspektionen', readAt: '2026-11-11T03:17:00Z' };

describe('suggestReason', () => {
  it('says a regulation listed through one licence line, and its term', () => {
    expect(suggestReason([funds], 'Example Fonder AB', null, en.t, en.ctx)).toBe('Within the scope of its licence Tillstånd att driva fondverksamhet, which brings Funds into scope.');
  });

  it('names two or more licence lines together', () => {
    const two: Basis = { term: 'Securities', lines: ['Värdepappersbolag', 'Portföljförvaltning'] };
    expect(suggestReason([two], 'Example Bank AB', null, en.t, en.ctx)).toBe('Within the scope of its licences Värdepappersbolag and Portföljförvaltning, which bring Securities into scope.');
    const three: Basis = { term: 'Securities', lines: ['A', 'B', 'C'] };
    expect(suggestReason([three], 'Example Bank AB', null, sv.t, sv.ctx)).toBe('Inom ramen för bolagets tillstånd A, B och C, som omfattar området Securities.');
  });

  it("says a regulation listed through the bank's scope, naming the company", () => {
    expect(suggestReason([aml], 'Example Fonder AB', null, en.t, en.ctx)).toBe("Within the bank's scope Anti-money laundering, which includes Example Fonder AB.");
    expect(suggestReason([aml], 'Example Fonder AB', null, sv.t, sv.ctx)).toBe('Inom bankens regulatoriska omfattning Anti-money laundering, som omfattar Example Fonder AB.');
  });

  it('uses the one basis that regulations share, and says several together', () => {
    expect(suggestReason([funds, { ...funds, lines: [...funds.lines] }], 'Example Fonder AB', null, en.t, en.ctx)).toBe(
      'Within the scope of its licence Tillstånd att driva fondverksamhet, which brings Funds into scope.',
    );
    expect(suggestReason([funds, aml], 'Example Fonder AB', null, en.t, en.ctx)).toBe("Within the scope of Example Fonder AB's licences and the bank's regulatory scope.");
    expect(suggestReason([funds, aml], 'Example Fonder AB', null, sv.t, sv.ctx)).toBe('Inom ramen för tillstånden hos Example Fonder AB och bankens regulatoriska omfattning.');
    // Nothing known about the bases (a decision over more regulations than one read holds).
    expect(suggestReason([], 'Example Fonder AB', null, en.t, en.ctx)).toBe("Within the scope of Example Fonder AB's licences and the bank's regulatory scope.");
  });

  it('adds where and when the register facts were read, when the company has them', () => {
    expect(suggestReason([funds], 'Example Fonder AB', read, en.t, en.ctx)).toBe(
      "Within the scope of its licence Tillstånd att driva fondverksamhet, which brings Funds into scope. Read from Finansinspektionen's register on 11 Nov 2026.",
    );
    expect(suggestReason([funds], 'Example Fonder AB', read, sv.t, sv.ctx)).toBe(
      'Inom ramen för bolagets tillstånd Tillstånd att driva fondverksamhet, som omfattar området Funds. Enligt registret hos Finansinspektionen, hämtat 11 nov. 2026.',
    );
  });

  it("gives the bank's scope no register sentence, since the scope is not read from the register", () => {
    expect(suggestReason([aml], 'Example Fonder AB', read, en.t, en.ctx)).toBe("Within the bank's scope Anti-money laundering, which includes Example Fonder AB.");
    expect(suggestReason([aml], 'Example Fonder AB', read, sv.t, sv.ctx)).toBe('Inom bankens regulatoriska omfattning Anti-money laundering, som omfattar Example Fonder AB.');
    // Several bases name the company's licences, so the register sentence follows.
    expect(suggestReason([funds, aml], 'Example Fonder AB', read, en.t, en.ctx)).toBe(
      "Within the scope of Example Fonder AB's licences and the bank's regulatory scope. Read from Finansinspektionen's register on 11 Nov 2026.",
    );
  });

  it("reads a regulation's basis from its regime and register lines", () => {
    expect(basisOf({ through: { term: { key: 'funds', label: 'Funds', kind: null, dimension: 'regime' }, lines: ['Tillstånd att driva fondverksamhet'] } })).toEqual(funds);
  });
});
