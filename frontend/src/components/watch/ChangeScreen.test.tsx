import { render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { ChangeDetail } from '@/features/watch/api';
import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';
import { defaultFormatContext } from '@/shared/utils/format';

import { ChangeDocuments, fetchedLine, presentDocument } from './ChangeDocuments';
import { ChangeObligations, presentObligationLink } from './ChangeObligations';
import { ChangeScreen, detailFacts, headMeta, presentChangeDetail, presentScopeTerms } from './ChangeScreen';
import { ChangeTimeline, eventMeta, nextEventId } from './ChangeTimeline';

// /watch/[changeId] (design/screens/tenant-change.html): the header's pills
// in the card's slot order, partial dates at the precision the source
// stated, documents that render as text, obligation links that say whether a
// person settled them, and every state the card names.

const t = createT('en');
const sv = createT('sv');
const ctx = defaultFormatContext;
const svCtx = { ...defaultFormatContext, locale: 'sv' as const };
const TODAY = new Date(Date.UTC(2026, 8, 19));

const change: ChangeDetail = {
  id: 'c-1',
  stableKey: 'fi:2026:analys-betalning',
  title: 'FI adopts amended rules on paying for investment research',
  status: 'active',
  authorityId: 'a-1',
  authorityLabel: 'Finansinspektionen',
  changeType: { key: 'adopted', kind: 'adopted', label: 'Adopted rule' },
  flags: [{ ref: { key: 'inducements', kind: null, label: 'Inducements' }, confidence: 0.74, suggested: true }],
  terms: [{ ref: { key: 'securities', kind: null, label: 'Securities' }, confidence: null, suggested: false }],
  suggestedUrgency: { key: 'act_now', kind: null, label: 'Act now' },
  summary: 'FI’s board decided on 15 September 2026 to amend three regulations.',
  soWhatDraft: 'Teams that pay for external research should confirm the criteria exist.',
  publishedOn: '2026-09-15',
  publishedPrecision: 'day',
  keyDate: '2026-10-01',
  keyDateLabel: 'In force',
  keyDatePrecision: 'day',
  recurrenceRule: null,
  sourceLabel: 'fi.se, press release',
  sourceUrl: 'https://www.fi.se/',
  origin: 'agent',
  model: 'Research agent 0.4',
  agentRunId: 'run-1',
  firstSeenAt: '2026-09-16T06:02:00Z',
  duplicateCount: 1,
  inFootprint: true,
  events: [
    { id: 'e-1', label: 'Consultation closed', eventDate: '2026-06-01', datePrecision: 'day', occurred: true, sortOrder: 1, sourceUrl: null },
    { id: 'e-2', label: 'In force', eventDate: '2026-10-01', datePrecision: 'day', occurred: false, sortOrder: 2, sourceUrl: null },
    { id: 'e-3', label: 'First annual assessment due', eventDate: '2027-10', datePrecision: 'quarter', occurred: false, sortOrder: 3, sourceUrl: null },
    { id: 'e-4', label: 'FI follow-up', eventDate: null, datePrecision: null, occurred: false, sortOrder: 4, sourceUrl: null },
  ],
  documents: [
    {
      id: 'd-1',
      url: 'https://www.fi.se/press/',
      title: 'FI ändrar regler om betalning för analys',
      publisher: 'Finansinspektionen',
      fetchedAt: '2026-09-16T06:58:00Z',
      isPrimary: true,
      isDuplicate: false,
      riskFlags: [],
    },
    {
      id: 'd-2',
      url: 'https://www.di.se/analys/',
      title: 'FI skärper analysreglerna',
      publisher: 'Dagens Industri',
      fetchedAt: '2026-09-16T07:00:00Z',
      isPrimary: false,
      isDuplicate: true,
      riskFlags: ['prompt_injection'],
    },
  ],
  obligations: [
    {
      obligationId: 'o-1',
      title: 'Pay for third-party research only under the permitted models',
      instrumentShortName: 'FFFS 2017:2',
      refLabel: '9 kap. 6 §',
      confidence: 0.86,
      confirmed: false,
      origin: 'agent',
    },
    {
      obligationId: 'o-2',
      title: 'Assess suitability when giving investment advice',
      instrumentShortName: 'LVM',
      refLabel: '9 kap.',
      confidence: null,
      confirmed: true,
      origin: 'user',
    },
  ],
  case: {
    id: 'case-1',
    category: 'new',
    allowedTransitions: [],
    footprintMatch: true,
    obligationDecisions: [],
    ownerId: null,
    soWhatConfirmed: false,
    soWhatConfirmedAt: null,
    soWhatText: 'Teams that pay for external research should confirm the criteria exist.',
    urgency: null,
    urgencyConfirmed: false,
  },
} as ChangeDetail;

function shell(children: ReactNode): ReactNode {
  const { wrapper: Query } = queryWrapper();
  return (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
}

/** The session read answers a signed-in reader; only the change read is scripted per test. */
const SESSION = { user: { locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, enrolmentPending: false, permissions: ['watch.read'] };

function serve(answer: Answer): Sent[] {
  return installAdapter((sent) => (sent.path.startsWith('/api/v1/changes/') ? answer : { status: 200, data: SESSION }));
}

function renderScreen(): void {
  render(shell(<ChangeScreen changeId="c-1" />));
}

describe('the change header', () => {
  it('puts the pills in the card’s slot order, workflow status last', () => {
    expect(presentChangeDetail(change, t).map((pill) => [pill.label, pill.tone])).toEqual([
      ['Adopted rule', 'notice'],
      ['Act now', 'negative'],
      ['Inducements', 'brand'],
      ['Suggested by the agent', 'information'],
      ['Needs triage', 'information'],
    ]);
  });

  it('takes the urgency from this bank’s case once it has one', () => {
    const ours = { ...change, case: { ...change.case!, urgency: { key: 'monitor', kind: null, label: 'Monitor' } } };
    expect(detailFacts(ours, t).urgency).toEqual({ key: 'monitor', kind: 'monitor', label: 'Monitor' });
    // A key outside the severity scale gets no pill rather than a guessed tone.
    expect(detailFacts({ ...change, suggestedUrgency: { key: 'someday', kind: null, label: 'Someday' }, case: null }, t).urgency).toBeUndefined();
  });

  it('a change a library editor registered carries no suggestion marker', () => {
    expect(presentChangeDetail({ ...change, origin: 'user', case: null }, t).map((pill) => pill.label)).toEqual(['Adopted rule', 'Act now', 'Inducements']);
  });

  it('reads the authority, the published date, the merged duplicates and who found it', () => {
    expect(headMeta(change, t, ctx)).toEqual([
      'Finansinspektionen',
      'Published 15 Sept 2026',
      '1 duplicate merged',
      'Found by Research agent 0.4, 16 Sept 2026',
    ]);
  });

  it('says when the change is outside our scope, and leaves out what the source did not state', () => {
    const bare = { ...change, publishedOn: null, duplicateCount: 0, model: null, inFootprint: false };
    expect(headMeta(bare, t, ctx)).toEqual(['Finansinspektionen', 'Outside our scope']);
  });

  it('a scope term is a brand pill, and an empty scope means no restriction', () => {
    expect(presentScopeTerms(change).map((pill) => [pill.label, pill.tone])).toEqual([['Securities', 'brand']]);
    expect(presentScopeTerms({ ...change, terms: [] })).toEqual([]);
  });
});

describe('the timeline', () => {
  it('renders each date at the precision the source stated, in English', () => {
    expect(eventMeta(change.events[0]!, t, ctx, TODAY)).toEqual(['1 Jun 2026']);
    expect(eventMeta(change.events[1]!, t, ctx, TODAY)).toEqual(['1 Oct 2026', 'in 12 days']);
    expect(eventMeta(change.events[2]!, t, ctx, TODAY)).toEqual(['Q4 2027']);
    expect(eventMeta(change.events[3]!, t, ctx, TODAY)).toEqual(['Date not set']);
  });

  it('renders the same dates in Swedish', () => {
    expect(eventMeta(change.events[1]!, sv, svCtx, TODAY)).toEqual(['1 okt. 2026', 'om 12 dagar']);
    expect(eventMeta(change.events[2]!, sv, svCtx, TODAY)).toEqual(['kv. 4 2027']);
    expect(eventMeta(change.events[3]!, sv, svCtx, TODAY)).toEqual(['Datum inte satt']);
    expect(eventMeta({ ...change.events[0]!, eventDate: '2026-06', datePrecision: 'month' }, sv, svCtx, TODAY)).toEqual(['juni 2026']);
  });

  it('marks what has happened and counts down to the first date still ahead', () => {
    render(shell(<ChangeTimeline events={change.events} today={TODAY} />));
    expect(nextEventId(change.events)).toBe('e-2');
    expect(nextEventId([])).toBeNull();
    expect(screen.getByText('Consultation closed').closest('li')).toHaveAttribute('data-event-occurred', '');
    expect(screen.getByText('In force').closest('li')).not.toHaveAttribute('data-event-occurred');
  });

  it('an empty timeline says so rather than looking broken', () => {
    render(shell(<ChangeTimeline events={[]} today={TODAY} />));
    expect(screen.getByText('No dates yet')).toBeInTheDocument();
  });
});

describe('the documents panel', () => {
  it('names the publisher and the fetch, and marks a merged duplicate', () => {
    expect(fetchedLine(change.documents[0]!, t, ctx)).toBe('Finansinspektionen, fetched 16 Sept 2026, 08:58');
    expect(presentDocument(change.documents[0]!, t)).toEqual([]);
    expect(presentDocument(change.documents[1]!, t).map((pill) => [pill.label, pill.tone])).toEqual([['Merged as duplicate', 'information']]);
  });

  it('falls back to the address when the page names no publisher, and to nothing when it was never fetched', () => {
    expect(fetchedLine({ ...change.documents[0]!, publisher: null }, t, ctx)).toBe('https://www.fi.se/press/, fetched 16 Sept 2026, 08:58');
    expect(fetchedLine({ ...change.documents[0]!, fetchedAt: null, publisher: null }, t, ctx)).toBeNull();
  });

  it('renders the fetched title as text and warns about a screening hit', () => {
    render(shell(<ChangeDocuments documents={change.documents} />));
    const link = screen.getByRole('link', { name: 'FI skärper analysreglerna' });
    expect(link).toHaveAttribute('href', 'https://www.di.se/analys/');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByText('Flagged when screened. Open the publisher’s page with care.')).toBeInTheDocument();
  });

  it('a document with no title is reachable by its address', () => {
    render(shell(<ChangeDocuments documents={[{ ...change.documents[0]!, title: null }]} />));
    expect(screen.getByRole('link', { name: 'https://www.fi.se/press/' })).toBeInTheDocument();
  });

  it('an empty panel says so', () => {
    render(shell(<ChangeDocuments documents={[]} />));
    expect(screen.getByText('No source page yet')).toBeInTheDocument();
  });
});

describe('the obligations affected', () => {
  it('shows a suggestion with the agent’s confidence and a confirmed link as settled', () => {
    expect(presentObligationLink(change.obligations[0]!, t).map((pill) => [pill.label, pill.tone])).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Suggested, 86% match', 'information'],
    ]);
    expect(presentObligationLink(change.obligations[1]!, t).map((pill) => [pill.label, pill.tone])).toEqual([
      ['LVM', 'brand'],
      ['Confirmed by a library editor', 'positive'],
    ]);
  });

  it('a suggestion nobody scored still says who put it forward', () => {
    expect(presentObligationLink({ ...change.obligations[0]!, confidence: null }, t)[1]!.label).toBe('Suggested by the agent');
  });

  it('links into the obligation and offers no control that would settle a library fact', () => {
    render(shell(<ChangeObligations obligations={change.obligations} />));
    expect(screen.getByRole('link', { name: 'Pay for third-party research only under the permitted models' })).toHaveAttribute('href', '/inventory/obligations/o-1');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('an obligation nothing is linked to says so', () => {
    render(shell(<ChangeObligations obligations={[]} />));
    expect(screen.getByText('No obligation is linked yet')).toBeInTheDocument();
  });
});

describe('the change screen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads the change and lays out the card’s panels', async () => {
    serve({ status: 200, data: change });
    renderScreen();

    expect(await screen.findByRole('heading', { level: 1, name: change.title })).toBeInTheDocument();
    for (const title of ['What happened', 'Classification', 'Obligations affected', 'Timeline', 'Documents', 'Record']) {
      expect(screen.getByRole('heading', { level: 2, name: title })).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Source: fi.se, press release' })).toHaveAttribute('href', 'https://www.fi.se/');
    expect(screen.getByText('fi:2026:analys-betalning')).toBeInTheDocument();
  });

  it('marks the type and the urgency as suggestions, and offers no control that confirms one', async () => {
    serve({ status: 200, data: change });
    renderScreen();

    const classification = (await screen.findByRole('heading', { level: 2, name: 'Classification' })).closest('section')!;
    expect(within(classification).getAllByText('suggested')).toHaveLength(2);
    expect(within(classification).queryByRole('button')).not.toBeInTheDocument();
    expect(within(classification).getByText('Securities')).toHaveAttribute('data-pill', 'brand');
  });

  it('a change with no scope term says the scope does not restrict it', async () => {
    serve({ status: 200, data: { ...change, terms: [] } });
    renderScreen();
    expect(await screen.findByText('Not specific')).toBeInTheDocument();
  });

  it('a wording this bank confirmed drops the "suggested" marker on the urgency', async () => {
    serve({ status: 200, data: { ...change, origin: 'user', case: { ...change.case!, urgencyConfirmed: true } } });
    renderScreen();
    await screen.findByRole('heading', { level: 1, name: change.title });
    expect(screen.queryByText('suggested')).not.toBeInTheDocument();
  });

  it('a change at an address this bank cannot reach is not found, never restricted', async () => {
    serve({ status: 404, data: { code: 'not_found', detail: 'No such change.' } });
    renderScreen();
    expect(await screen.findByText('There is nothing at this address in your organisation.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to Watch' })).toHaveAttribute('href', '/watch');
  });

  it('a reader without the permission gets the Restricted screen from the code, not the detail', async () => {
    serve({ status: 403, data: { code: 'permission_denied', detail: 'You do not have access.', requiredPermission: 'watch.read' } });
    renderScreen();
    await waitFor(() => expect(screen.getByText(/watch\.read|Watch read|read watch/i)).toBeInTheDocument());
  });

  it('a read that fails offers the way to try again', async () => {
    serve({ status: 500, data: { code: 'server_error', detail: '' } });
    renderScreen();
    expect(await screen.findByText('Could not load this change')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('says it is loading before the read answers', () => {
    serve({ status: 200, data: change });
    renderScreen();
    expect(screen.getByRole('status')).toHaveAttribute('data-loading-state');
  });
});
