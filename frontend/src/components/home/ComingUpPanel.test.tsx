import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { RoadmapItem } from '@/features/home/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { defaultFormatContext } from '@/shared/utils/format';

import { ComingUpPanel } from './ComingUpPanel';

// "Coming up" on Today and the briefing (HOM-01, HOM-03, INV-S10): a date is
// printed only as exactly as the source stated it, and only a date stated to
// the day counts the days left to it.

const byDay: RoadmapItem = {
  id: 'change_date:c-1',
  kind: 'regulatory',
  itemType: 'change_date',
  date: '2026-10-01',
  datePrecision: 'day',
  quarter: '2026-Q4',
  label: 'In force',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'new',
  urgency: { key: 'act_now', kind: null, label: 'Act now' },
  sourceLabel: 'Finansinspektionen',
  changeId: 'c-1',
  owner: null,
  subject: null,
  obligations: [],
};

const byQuarter: RoadmapItem = {
  ...byDay,
  id: 'change_date:c-2',
  date: '2026-11-15',
  datePrecision: 'quarter',
  title: 'Amended reporting of securities financing transactions',
  changeId: 'c-2',
};

function row(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-roadmap-item="${id}"]`);
  if (found === null) throw new Error(`no row ${id}`);
  return found;
}

beforeEach(() => {
  vi.useFakeTimers({ now: new Date('2026-09-21T09:00:00Z'), toFake: ['Date'] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ComingUpPanel', () => {
  it('prints a quarter-precision date as its quarter and counts no days to it', () => {
    render(
      <LocaleProvider locale="en">
        <ComingUpPanel items={[byDay, byQuarter]} roadmapCount={2} ctx={defaultFormatContext} />
      </LocaleProvider>,
    );

    expect(row(byQuarter.id)).toHaveTextContent('Q4 2026');
    expect(row(byQuarter.id)).not.toHaveTextContent('15 Nov 2026');
    expect(row(byQuarter.id)).not.toHaveTextContent(/\bin \d+ days?\b/);

    expect(row(byDay.id)).toHaveTextContent('1 Oct 2026');
    expect(row(byDay.id)).toHaveTextContent('in 10 days');
    expect(screen.getByRole('link', { name: byQuarter.title })).toHaveAttribute('href', '/watch/c-2');
  });

  it('reads the quarter in the language of the person reading', () => {
    render(
      <LocaleProvider locale="sv">
        <ComingUpPanel items={[byQuarter]} ctx={{ ...defaultFormatContext, locale: 'sv' }} />
      </LocaleProvider>,
    );

    expect(row(byQuarter.id)).toHaveTextContent('kv. 4 2026');
  });
});
