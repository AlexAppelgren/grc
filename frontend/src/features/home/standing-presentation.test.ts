import { describe, expect, it } from 'vitest';

import type { VocabularyRow } from '@/features/vocabularies/types';

import { presentStanding, type Standing } from './standing-presentation';

function status(key: string, kind: string, extra: Partial<VocabularyRow> = {}): VocabularyRow {
  return { key, kind, label: key, labels: {}, usageNote: '', sortOrder: 0, active: true, isSystem: true, isDefault: false, usageCount: 0, extra: {}, ...extra };
}

const standing: Standing = { applying: 14, compliant: 8, partly: 3, gap: 1, notAssessed: 2, openGaps: 6 };
const statuses = [status('compliant', 'compliant'), status('partly_compliant', 'partly'), status('gap', 'gap'), status('not_assessed', 'not_assessed')];
const nothing: Standing = { applying: 0, compliant: 0, partly: 0, gap: 0, notAssessed: 0, openGaps: 0 };

describe('presentStanding', () => {
  it('lists the four categories in the fixed order, each in its own tone', () => {
    const presented = presentStanding(standing, statuses);
    expect(presented.lines.map((line) => [line.key, line.count, line.tone])).toEqual([
      ['compliant', 8, 'positive'],
      ['partly', 3, 'warning'],
      ['gap', 1, 'negative'],
      ['not_assessed', 2, 'information'],
    ]);
    expect(presented.lines[0]?.color).toMatch(/^var\(--.+\)$/);
    expect(presented.lines.map((line) => line.message)).toEqual([
      'today.standing.compliant',
      'today.standing.partly',
      'today.standing.gap',
      'today.standing.notAssessed',
    ]);
  });

  it('links each category to the inventory filtered to the obligations that apply in the status of that category, by key', () => {
    const presented = presentStanding(standing, statuses);
    expect(presented.applyingHref).toBe('/inventory?applicability=applies');
    expect(presented.lines.map((line) => line.href)).toEqual([
      '/inventory?applicability=applies&complianceStatus=compliant',
      '/inventory?applicability=applies&complianceStatus=partly_compliant',
      '/inventory?applicability=applies&complianceStatus=gap',
      '/inventory?applicability=applies&complianceStatus=not_assessed',
    ]);
    expect(presented.gapsHref).toBe('/gaps');
  });

  it("prefers the category's system row over a status the bank added under it, and skips a retired one", () => {
    const rows = [status('partly_retired', 'partly', { active: false }), status('partly_own', 'partly', { isSystem: false }), status('partly_compliant', 'partly')];
    expect(presentStanding(standing, rows).lines[1]?.href).toBe('/inventory?applicability=applies&complianceStatus=partly_compliant');
    expect(presentStanding(standing, [status('partly_own', 'partly', { isSystem: false })]).lines[1]?.href).toBe(
      '/inventory?applicability=applies&complianceStatus=partly_own',
    );
  });

  it('draws a category with no status to filter by as plain text, and every category plain while the list loads', () => {
    expect(presentStanding(standing, [status('compliant', 'compliant')]).lines.map((line) => line.href !== null)).toEqual([true, false, false, false]);
    expect(presentStanding(standing, undefined).lines.every((line) => line.href === null)).toBe(true);
  });

  it('is empty when nothing applies and no gap is open, and not when either is there', () => {
    expect(presentStanding(nothing, statuses).empty).toBe(true);
    expect(presentStanding({ ...nothing, openGaps: 1 }, statuses).empty).toBe(false);
    expect(presentStanding(standing, statuses).empty).toBe(false);
  });
});
