import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { withPanels } from '@/features/register/testing';
import type { RegisterEntityStatus, RegisterEntry } from '@/features/register/types';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ObligationScreen, diffSentence, effectiveIn, languageChoices, originalLanguage, summaryChoices, textIn } from './ObligationScreen';
import type { LocalizedText, ObligationDetail, ObligationVersionRow, VersionDiff } from '@/features/library/types';
import { defaultFormatContext } from '@/shared/utils/format';

// The obligation page (design/screens/tenant-obligation.html): the head with
// its link back to the regulation, "In plain words" (bleqq's summary, never
// called the original), "The rule's own words", then five cards in their
// order. Nothing here writes the library, and nothing claims the duty applies.

// The register's parts, participants, tags and comments are filled by their own
// packages and tested in their own files. Here each stands in as a marker, so
// the page's mount points, their cards and their order are what the tests read.
// "Our position" is drawn for real: its blocks are the page's own.
const PANELS = ['Handle', 'Gaps', 'Participants', 'Units', 'History', 'Tags', 'Comments'] as const;
function marker(name: string) {
  return {
    [`Obligation${name}Panel`]: ({ obligationId }: { obligationId: string }) => <span data-panel-mount={name} data-for={obligationId} />,
  };
}
vi.mock('./ObligationStatusPanel', async (actual) => ({ ...(await actual<Record<string, unknown>>()), ...marker('Handle') }));
vi.mock('./ObligationGapsPanel', () => marker('Gaps'));
vi.mock('./ObligationParticipantsPanel', () => marker('Participants'));
vi.mock('./ObligationUnitsPanel', () => marker('Units'));
vi.mock('./ObligationHistoryPanel', () => marker('History'));
vi.mock('./ObligationTagsPanel', () => marker('Tags'));
vi.mock('./ObligationCommentsPanel', () => marker('Comments'));

const t = createT('en');

// The summary bleqq wrote in Swedish, and its English machine translation.
const sv: LocalizedText = { text: 'Investeringsanalys från tredje part får tas emot endast…', language: 'sv', isOriginal: true, isMachine: false };
const en: LocalizedText = { text: 'Research from third parties may be received only if…', language: 'en', isOriginal: false, isMachine: true };

// Version 1 was seeded, so nobody approved it; version 2 a person approved.
// Every instant is fixed: nothing on this page reads today's date.
const nobody = { verifiedOrigin: '', confirmedByAgent: null, proposedByAgent: null };
const seeded: ObligationVersionRow = {
  versionNumber: 1,
  effectiveFrom: null,
  effectiveTo: { date: '2026-09-30', precision: 'day' },
  approvedAt: null,
  ...nobody,
};
const byPerson: ObligationVersionRow = {
  versionNumber: 2,
  effectiveFrom: { date: '2026-10-01', precision: 'day' },
  effectiveTo: null,
  approvedAt: '2026-08-17T14:02:11Z',
  verifiedOrigin: 'user',
  confirmedByAgent: null,
  proposedByAgent: null,
};
// The same version 2, proposed by one agent and confirmed by an independent one.
const byAgents: ObligationVersionRow = {
  ...byPerson,
  verifiedOrigin: 'agent',
  confirmedByAgent: { id: 'ag-2', key: 'library-confirmer' },
  proposedByAgent: { id: 'ag-1', key: 'watch-sweeper' },
};
const MACHINE_CONFIRMED = 'Machine-confirmed 17 Aug 2026: proposed by watch-sweeper, confirmed by library-confirmer';

// The section the duty cites: the authority published it in Swedish, and the library
// holds an English machine translation beside it.
const section = {
  id: 'pv-6',
  refLabel: '9 kap. 6 §',
  path: 'FFFS 2017:2 > 9 kap. > 6 §',
  heading: 'Betalning för analys',
  texts: [
    { text: 'Investeringsanalys från tredje part får tas emot endast om den betalas med institutets egna medel.', language: 'sv', isOriginal: true, isMachine: false },
    { text: "Investment research from a third party may be received only if it is paid from the institution's own resources.", language: 'en', isOriginal: false, isMachine: true },
  ],
};

const research: ObligationDetail = {
  id: 'ob-1',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false },
  instrument: {
    id: 'in-1',
    key: 'fffs-2017-2',
    shortName: 'FFFS 2017:2',
    officialRef: 'FFFS 2017:2',
    name: { text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false },
    implementsNote: 'MiFID II delegated directive (EU) 2017/593',
  },
  regime: { key: 'securities', kind: null, label: 'Securities' },
  bindingLevel: { key: 'authority_regulation', kind: null, label: 'FI regulation' },
  binding: true,
  dutyType: { key: 'governance', kind: null, label: 'Governance' },
  productScope: 'Third-party research',
  triggerFrequency: 'Annual assessment from 1 October 2026',
  retention: '5 years',
  sanctionExposure: 'FI remark, warning or sanction fee',
  tags: [{ key: 'research', kind: null, label: 'Research' }],
  tenantTags: [],
  privateToUs: false,
  scope: [
    { dimension: { key: 'service_type', kind: null, label: 'Service' }, terms: [{ key: 'advice', kind: null, label: 'Advice' }], allSelected: false },
    { dimension: { key: 'client_category', kind: null, label: 'Client category' }, terms: [], allSelected: false },
  ],
  inFootprint: true,
  outsideReason: [],
  summary: en,
  translations: [sv, en],
  version: seeded,
  versions: [seeded, byPerson],
  related: [
    {
      id: 'ob-2',
      title: { text: 'Disclose all costs and charges', language: 'en', isOriginal: true, isMachine: false },
      instrument: { id: 'in-1', key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
      relation: { key: 'related', kind: null, label: 'Related' },
      binding: true,
    },
  ],
  provenance: {
    sourceUrl: 'https://www.fi.se/',
    sourceLabel: 'FFFS 2017:2, 9 kap. 6 §',
    lastVerifiedAt: '2026-06-30T07:12:44Z',
    verifiedBy: null,
    createdAt: '2026-03-12T08:45:03Z',
    createdOrigin: 'agent',
    createdModel: 'agent pipeline 0.3',
    ...nobody,
  },
  applicability: 'under_assessment',
  complianceStatus: null,
  firstLineOwner: null,
  ownerTeam: null,
  provisions: [section],
};

const NOT_ASSESSED = { key: 'not_assessed', kind: 'not_assessed', label: 'Not assessed' };
const PARTLY = { key: 'partly_compliant', kind: 'partly', label: 'Partly compliant' };
const COMPLIANT = { key: 'compliant', kind: 'compliant', label: 'Compliant' };
const SARA = { id: 'p-sara', name: 'Sara Lindqvist' };

function entity(id: string, name: string, patch: Partial<RegisterEntityStatus>): RegisterEntityStatus {
  return {
    orgUnitId: id,
    orgUnitName: name,
    applicability: 'applies',
    applicabilityReason: 'We give advice.',
    applicabilityDecidedAt: '2026-09-18T08:30:00Z',
    applicabilityDecidedBy: SARA,
    complianceStatus: COMPLIANT,
    statusNote: null,
    riskRating: null,
    owner: null,
    ownerTeam: null,
    process: null,
    system: null,
    evidenceLocation: null,
    nextReviewDate: null,
    version: 1,
    ...patch,
  };
}

/** Nobody at the bank has worked on the duty yet. */
const untouched: RegisterEntry = {
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
};
const SPAN = [
  { orgUnitId: 'e-bank', orgUnitName: 'Example Bank AB' },
  { orgUnitId: 'e-fonder', orgUnitName: 'Example Fonder AB' },
];
/** The bank applies and complies; the fund company is partly compliant, the weakest. */
const worked: RegisterEntry = {
  ...untouched,
  applicability: 'applies',
  complianceStatus: PARTLY,
  entities: [entity('e-bank', 'Example Bank AB', {}), entity('e-fonder', 'Example Fonder AB', { complianceStatus: PARTLY })],
  version: 3,
};

const ME = {
  user: { id: 'u1', name: 'Sara', locale: 'en' },
  tenant: { timezone: 'Europe/Stockholm' },
  permissions: ['library.read', 'problems.report'],
  enrolmentPending: false,
};

function renderIn(node: ReactNode, permissions: string[] = ['library.read', 'problems.report'], client?: QueryClient) {
  const { wrapper } = queryWrapper();
  const Wrapper = client === undefined ? (wrapper as (props: { children: ReactNode }) => ReactNode) : ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return render(
    <Wrapper>
      {
        <LocaleProvider locale="en">
          <PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>
        </LocaleProvider>
      }
    </Wrapper>,
  );
}

const versionDiff: VersionDiff = {
  fromVersion: 1,
  toVersion: 2,
  fromEffective: null,
  toEffective: { date: '2026-10-01', precision: 'day' },
  language: 'en',
  isMachine: true,
  fromConfirmation: null,
  toConfirmation: null,
  segments: [
    { op: 'equal', text: 'Research from third parties may be received only if…' },
    { op: 'insert', text: 'The institution sets criteria for an annual assessment.' },
  ],
};

/** The server: /me for the format context and the permissions, then the record, the register read, the diff and the report. */
function serve(answer: ObligationDetail | number, register: RegisterEntry | number = untouched, span: { orgUnitId: string; orgUnitName: string }[] = []) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/obligations/ob-1/register') {
      const nothingYet = { spannedEntities: span, problemReports: { items: [], total: 0 }, changes: { items: [], total: 0, openCount: 0 } };
      return typeof register === 'number' ? { status: register, data: { detail: 'no', code: 'server_error' } } : { status: 200, data: withPanels(register, nothingYet) };
    }
    if (sent.path === '/api/v1/obligations/ob-1/register/entities') return { status: 200, data: span };
    if (sent.path.endsWith('/diff')) return { status: 200, data: versionDiff };
    // The record's "Reported problems" (AUD-03): the bank has filed none on it.
    if (sent.method === 'get' && sent.path === '/api/v1/problem-reports') return { status: 200, data: { items: [], total: 0 } };
    if (sent.path === '/api/v1/obligations/ob-1/changes') return { status: 200, data: { items: [], total: 0, openCount: 0 } };
    if (sent.method === 'post' && sent.path === '/api/v1/problem-reports') return { status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } };
    if (typeof answer === 'number') return { status: answer, data: { detail: 'no', code: answer === 404 ? 'not_found' : 'server_error' } };
    // "As of" a date before version 2 is the same record read again; the
    // version in force is what the server decides, so the test answers what
    // the date asked for.
    const asOf = (sent.params as { asOf?: string } | null)?.asOf;
    if (asOf === '2026-10-01') return { status: 200, data: { ...answer, version: answer.versions[1] } };
    return { status: 200, data: answer };
  }, { me: ME });
}

const TITLE = 'Pay for third-party research only under the permitted models';
const CARDS = ['Our position', 'How we comply', 'The rule', 'Source and changes', 'People and discussion'];
const cardTitles = () => [...document.querySelectorAll<HTMLElement>('section > h2')].map((heading) => heading.textContent).filter((text) => text !== null && CARDS.includes(text));
const card = (title: string) => screen.getByRole('heading', { level: 2, name: title }).closest('section') as HTMLElement;
const mounts = (root: ParentNode = document) => [...root.querySelectorAll<HTMLElement>('[data-panel-mount]')].map((mount) => mount.dataset.panelMount);

describe('the summary\'s language chips', () => {
  it('names each language and nothing else, and offers the reader a language the version does not hold', () => {
    expect(summaryChoices([sv, en], 'en', 'en')).toEqual([
      { language: 'sv', label: 'Swedish', selected: false, hasText: true },
      { language: 'en', label: 'English', selected: true, hasText: true },
    ]);
    // A Swedish reader of a record with no Swedish text still gets a chip, and
    // it holds none. The names are in the reader's own language, not the text's.
    expect(summaryChoices([en], 'en', 'sv')).toEqual([
      { language: 'en', label: 'engelska', selected: true, hasText: true },
      { language: 'sv', label: 'svenska', selected: false, hasText: false },
    ]);
    expect(summaryChoices([], 'en', 'en')).toEqual([{ language: 'en', label: 'English', selected: true, hasText: false }]);
  });

  it('keeps the regulation page\'s chips, whose original is still marked', () => {
    expect(languageChoices([sv, en], 'en', 'en', t).map((choice) => choice.label)).toEqual(['Swedish, original', 'English']);
    expect(languageChoices([sv, en], 'sv', 'sv', createT('sv')).map((choice) => choice.label)).toEqual(['svenska, original', 'engelska']);
  });

  it('finds the text of a language, and the language bleqq wrote in', () => {
    expect(textIn([sv, en], 'sv')).toEqual(sv);
    expect(textIn([sv, en], 'fi')).toBeNull();
    expect(originalLanguage([en, sv])).toBe('sv');
    // No row is flagged: the first one stands in for it.
    expect(originalLanguage([en])).toBe('en');
    expect(originalLanguage([])).toBeNull();
  });
});

describe('ObligationScreen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('session-token');
  });

  it('heads the page with its pills, the regulation one click away, and the title', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });

    // Instrument, regime, binding level: brand, information, information (INV-S3).
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Securities', 'information'],
      ['Binding', 'information'],
    ]);
    // The regulation's short name goes back to the regulation's own page.
    const back = document.querySelector('[data-header-pills] [data-instrument-link]') as HTMLElement;
    expect(back).toHaveAttribute('href', '/inventory/instruments/in-1');
    expect(back).toHaveTextContent('FFFS 2017:2');
    // Nobody stands anywhere yet, so the head names no weakest company.
    expect(document.querySelector('[data-status-header]')).toBeNull();
  });

  it('names the weakest company beside the head once the bank stands somewhere', async () => {
    serve(research, worked, SPAN);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    const standing = (await screen.findByText('at Example Fonder AB, the weakest legal entity')).closest('[data-status-header]') as HTMLElement;
    expect(within(standing).getByText('Partly compliant')).toHaveAttribute('data-pill', 'warning');
    // The head's own pills stay three.
    expect(document.querySelectorAll('[data-header-pills] [data-pill]')).toHaveLength(3);
  });

  it('lays out the five cards in their order, for a worked and an untouched duty alike', async () => {
    for (const [register, span] of [
      [untouched, []],
      [worked, SPAN],
    ] as const) {
      resetApiForTests();
      tokenStore.set('session-token');
      serve(research, register, [...span]);
      const shown = renderIn(<ObligationScreen obligationId="ob-1" />);
      await screen.findByRole('heading', { level: 1, name: TITLE });
      await waitFor(() => expect(document.querySelector('[data-position-entity]')).not.toBeNull());
      expect(cardTitles()).toEqual(CARDS);
      // What each card holds, in its order.
      expect(mounts(card('How we comply'))).toEqual(['History', 'Handle', 'Gaps']);
      expect(card('The rule').querySelector('[data-scope-panel] + [data-duty-panel]')).not.toBeNull();
      expect(mounts(card('The rule'))).toEqual(['Tags']);
      const source = card('Source and changes');
      const parts = ['provenancePanel', 'relatedChanges', 'versionsPanel', 'relatedPanel'];
      expect(
        [...source.querySelectorAll<HTMLElement>('[data-provenance-panel], [data-related-changes], [data-versions-panel], [data-related-panel]')].map((part) => parts.find((name) => name in part.dataset)),
      ).toEqual(parts);
      expect(within(source).getByRole('button', { name: /^Reported problems/ })).toBeInTheDocument();
      expect(mounts(card('People and discussion'))).toEqual(['Participants', 'Comments']);
      expect(mounts().every((name) => document.querySelector(`[data-panel-mount="${name}"]`)?.getAttribute('data-for') === 'ob-1')).toBe(true);
      shown.unmount();
    }
  });

  it('draws "Our position" per company once the bank has worked on it, and one block for the whole duty before', async () => {
    serve(research, worked, SPAN);
    const shown = renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 3, name: 'Example Fonder AB' });
    const position = card('Our position');
    expect([...position.querySelectorAll('[data-position-entity] > h3')].map((heading) => heading.textContent)).toEqual([
      'The obligation as a whole',
      'Example Bank AB',
      'Example Fonder AB',
    ]);
    expect(position.querySelectorAll('[data-status-row]')).toHaveLength(2);
    shown.unmount();

    resetApiForTests();
    tokenStore.set('session-token');
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    expect(await screen.findByText('Nobody has decided yet.')).toBeInTheDocument();
    expect(card('Our position').querySelectorAll('[data-position-entity]')).toHaveLength(1);
    expect(card('Our position').querySelector('[data-status-row]')).toBeNull();
  });

  it('holds a standard\'s units in "Our position", and only a standard\'s', async () => {
    serve({ ...research, bindingLevel: { key: 'standard', kind: 'standard', label: 'Standard' } });
    const shown = renderIn(<ObligationScreen obligationId="ob-1" />);
    await waitFor(() => expect(card('Our position').querySelector('[data-panel-mount="Units"]')).not.toBeNull());
    shown.unmount();
    resetApiForTests();
    tokenStore.set('session-token');
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByText('Nobody has decided yet.');
    expect(document.querySelector('[data-panel-mount="Units"]')).toBeNull();
  });

  it('shows the rule, the duty, its scope and where it comes from, linked back to the regulation', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });

    // Scope: a brand pill per term, and plain words where the record restricts nothing.
    const scope = document.querySelector('[data-scope-panel]') as HTMLElement;
    expect(within(scope).getByText('Advice')).toHaveAttribute('data-pill', 'brand');
    expect(within(scope).getByText('Not client-specific')).toBeInTheDocument();
    expect(within(scope).getByText('Third-party research')).toBeInTheDocument();
    expect(within(scope).getByText('Research')).toHaveAttribute('data-pill', 'brand');

    const duty = document.querySelector('[data-duty-panel]') as HTMLElement;
    expect(within(duty).getByText('Governance')).toBeInTheDocument();
    expect(within(duty).getByText('5 years')).toBeInTheDocument();

    // Provenance: the regulation linked to its page, the source link, the verified date with no name, the draft's origin.
    const provenance = document.querySelector('[data-provenance-panel]') as HTMLElement;
    expect(within(provenance).getByRole('link', { name: 'FFFS 2017:2 om värdepappersrörelse' })).toHaveAttribute('href', '/inventory/instruments/in-1');
    const source = within(provenance).getByRole('link', { name: 'FFFS 2017:2, 9 kap. 6 §' });
    expect(source).toHaveAttribute('href', 'https://www.fi.se/');
    expect(source).toHaveAttribute('rel', 'noopener noreferrer');
    expect(document.querySelector('[data-last-verified]')?.textContent).toBe('30 Jun 2026');
    expect(screen.getByText(/agent pipeline 0\.3, through proposal review/)).toBeInTheDocument();

    // Versions stay open; the duties filed beside it are folded with their count.
    expect(document.querySelectorAll('[data-version-row]')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Related obligations (1)' }));
    expect(screen.getByRole('link', { name: 'Disclose all costs and charges' })).toHaveAttribute('href', '/inventory/obligations/ob-2');

    // No reform is filed against this duty: one line, no heading.
    expect(await screen.findByText('No change affects this obligation')).toBeInTheDocument();
  });

  it('calls the summary "In plain words", names its languages only, and labels a machine translation without calling anything the original', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });

    const summary = document.querySelector('[data-summary]') as HTMLElement;
    expect(within(summary).getByRole('heading', { level: 2, name: 'In plain words' })).toBeInTheDocument();
    expect(within(summary).getByText('Machine-translated from Swedish')).toBeInTheDocument();
    expect([...summary.querySelectorAll('[data-language-chips] button')].map((chip) => chip.textContent)).toEqual(['Swedish', 'English']);
    expect(summary.querySelector('[data-legal-text] [lang="en"]')?.textContent).toBe(en.text);
    expect(summary).not.toHaveTextContent(/original/i);

    fireEvent.click(within(summary).getByRole('button', { name: 'Swedish' }));
    await waitFor(() => expect(summary.querySelector('[data-legal-text] [lang="sv"]')?.textContent).toBe(sv.text));
    // The language bleqq wrote in carries no label at all.
    expect(summary.querySelector('[data-machine-translation]')).toBeNull();
    expect(summary).not.toHaveTextContent(/original/i);
  });

  it('says so when the version holds no summary in the reader\'s language, and offers the one it was written in', async () => {
    serve({ ...research, summary: sv, translations: [sv] });
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });

    fireEvent.click(within(document.querySelector('[data-language-chips]') as HTMLElement).getByRole('button', { name: 'English' }));
    expect(await screen.findByText('No English text yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: 'Read it in Swedish' }));
    await waitFor(() => expect(document.querySelector('[data-summary] [data-legal-text] [lang="sv"]')?.textContent).toBe(sv.text));
  });

  it('puts the rule\'s own words under the summary, labelled for what they are, and none for a duty that cites no provision', async () => {
    serve(research);
    const shown = renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });
    const words = document.querySelector('[data-summary] + [data-rule-words]') as HTMLElement;
    expect(within(words).getByRole('heading', { level: 2, name: "The rule's own words" })).toBeInTheDocument();
    expect(within(words).getByRole('heading', { level: 3, name: 'Betalning för analys' })).toBeInTheDocument();
    expect(words.querySelector('[data-provision-label]')?.textContent).toBe('Machine translation from Swedish. The original is authoritative.');
    expect(within(words).getByRole('link', { name: 'FFFS 2017:2' })).toHaveAttribute('href', '/inventory/instruments/in-1');
    fireEvent.click(within(words).getByRole('button', { name: 'Swedish, original' }));
    expect(words.querySelector('[data-provision-label]')?.textContent).toBe('Swedish, original');
    shown.unmount();

    resetApiForTests();
    tokenStore.set('session-token');
    serve({ ...research, provisions: [] });
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });
    expect(document.querySelector('[data-rule-words]')).toBeNull();
  });

  it('leads the head of the bank\'s own record with "Private to us", its instrument outlined (OWN-04)', async () => {
    serve({ ...research, privateToUs: true });
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1 });
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill'), pill.hasAttribute('data-outlined')])).toEqual([
      ['Private to us', 'information', true],
      ['FFFS 2017:2', 'information', true],
      ['Securities', 'information', false],
      ['Binding', 'information', false],
    ]);
  });

  it('reads "Standard" in the binding slot of a duty under a standard, never "Guidance, comply or explain"', async () => {
    serve({ ...research, bindingLevel: { key: 'standard', kind: 'standard', label: 'Standard edition' }, binding: false });
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1 });
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Securities', 'information'],
      ['Standard', 'information'],
    ]);
  });

  it('reads a record with no title, no lineage and nobody named as verifier', async () => {
    serve({
      ...research,
      title: null,
      productScope: '',
      triggerFrequency: '',
      retention: '',
      sanctionExposure: '',
      tags: [],
      related: [],
      versions: [],
      instrument: { ...research.instrument, name: null, implementsNote: '' },
      provenance: { ...research.provenance, lastVerifiedAt: null, createdOrigin: 'user', createdModel: '' },
    });
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Third-party payments' });
    expect(screen.getByText('Not verified yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Related obligations (0)' }));
    expect(screen.getByText('The library files no other duty beside this one.')).toBeInTheDocument();
    expect(screen.getByText(/^12 Mar 2026.*through proposal review$/)).toBeInTheDocument();
  });

  describe('a version independent agents confirmed', () => {
    const sara = { id: 'u-9', name: 'Sara Lindqvist' };
    const confirmedByAgents = { verifiedOrigin: 'agent', confirmedByAgent: byAgents.confirmedByAgent, proposedByAgent: byAgents.proposedByAgent };

    async function open(record: ObligationDetail) {
      serve(record);
      renderIn(<ObligationScreen obligationId="ob-1" />);
      await screen.findByRole('heading', { level: 1, name: TITLE });
    }

    it('reads machine-confirmed where a person\'s verification would, when a person last verified the record before it', async () => {
      // Sara verified the record on 30 June; the agents confirmed version 2 in August, and it is in force.
      await open({
        ...research,
        version: byAgents,
        versions: [seeded, byAgents],
        provenance: { ...research.provenance, verifiedBy: sara, ...confirmedByAgents },
      });
      const verified = document.querySelector('[data-last-verified]');
      expect(verified?.textContent).toBe(MACHINE_CONFIRMED);
      expect(verified).toHaveAttribute('data-machine-confirmed');
      expect(screen.queryByText(/Sara Lindqvist/)).not.toBeInTheDocument();
      expect(document.querySelector('[data-version-row="2"] [data-machine-confirmed]')?.textContent).toBe(MACHINE_CONFIRMED);
      expect(document.querySelector('[data-version-row="1"] [data-machine-confirmed]')).toBeNull();
    });

    it('says in the "Show what changed" banner that agents confirmed the newer wording', async () => {
      await open({ ...research, version: byAgents, versions: [seeded, byAgents], provenance: { ...research.provenance, ...confirmedByAgents } });
      fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
      await waitFor(() => expect(document.querySelector('[data-diff-banner]')).toBeInTheDocument());
      expect(document.querySelector('[data-diff-banner] [data-machine-confirmed]')?.textContent).toBe(MACHINE_CONFIRMED);
    });

    it('labels the version before it takes effect, beside the person\'s verification of the one in force', async () => {
      await open({ ...research, versions: [seeded, byAgents], provenance: { ...research.provenance, verifiedBy: sara } });
      const verified = document.querySelector('[data-last-verified]');
      expect(verified?.textContent).toBe('30 Jun 2026 by Sara Lindqvist');
      expect(verified).not.toHaveAttribute('data-machine-confirmed');
      expect(document.querySelector('[data-version-row="2"] [data-machine-confirmed]')?.textContent).toBe(MACHINE_CONFIRMED);
    });

    it('gives way in "Last verified" once a person re-verifies the record, while the version still says who approved it', async () => {
      await open({
        ...research,
        version: byAgents,
        versions: [seeded, byAgents],
        provenance: { ...research.provenance, lastVerifiedAt: '2026-12-01T09:00:00Z', verifiedBy: sara, ...confirmedByAgents },
      });
      const verified = document.querySelector('[data-last-verified]');
      expect(verified?.textContent).toBe('1 Dec 2026 by Sara Lindqvist');
      expect(verified).not.toHaveAttribute('data-machine-confirmed');
      expect(document.querySelector('[data-version-row="2"] [data-machine-confirmed]')?.textContent).toBe(MACHINE_CONFIRMED);
      expect(screen.queryByText('Approved 17 Aug 2026')).not.toBeInTheDocument();
    });

    it('keeps labelling a version not yet in force after a person re-verifies the wording that is', async () => {
      // Sara checked version 1 in December; version 2, which the agents confirmed in
      // August, takes effect in March and no person has read it.
      const march = { date: '2027-03-01', precision: 'day' as const };
      const inForce = { ...seeded, effectiveTo: { date: '2027-02-28', precision: 'day' as const } };
      await open({
        ...research,
        version: inForce,
        versions: [inForce, { ...byAgents, effectiveFrom: march }],
        provenance: { ...research.provenance, lastVerifiedAt: '2026-12-01T09:00:00Z', verifiedBy: sara },
      });
      expect(document.querySelector('[data-last-verified]')?.textContent).toBe('1 Dec 2026 by Sara Lindqvist');
      expect(document.querySelector('[data-version-row="2"] [data-machine-confirmed]')?.textContent).toBe(MACHINE_CONFIRMED);
      expect(screen.queryByText('Approved 17 Aug 2026')).not.toBeInTheDocument();
    });

    it('never gives way to a later date nobody signed', async () => {
      // A seeded stamp carries a date and no name: it is nobody's verification.
      await open({
        ...research,
        version: byAgents,
        versions: [seeded, byAgents],
        provenance: { ...research.provenance, lastVerifiedAt: '2026-12-01T09:00:00Z', verifiedBy: null, ...confirmedByAgents },
      });
      const verified = document.querySelector('[data-last-verified]');
      expect(verified?.textContent).toBe(MACHINE_CONFIRMED);
      expect(verified).toHaveAttribute('data-machine-confirmed');
    });

    it('reads a person\'s approval as it always has', async () => {
      await open({ ...research, version: byPerson, versions: [seeded, byPerson] });
      expect(document.querySelector('[data-machine-confirmed]')).toBeNull();
      expect(document.querySelector('[data-version-row="2"]')).toHaveTextContent('Approved 17 Aug 2026');
    });
  });

  it('renders Not found for an id this bank cannot read, and the error state otherwise', async () => {
    serve(404);
    const gone = renderIn(<ObligationScreen obligationId="ob-1" />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Inventory' })).toHaveAttribute('href', '/inventory');
    gone.unmount();

    resetApiForTests();
    tokenStore.set('session-token');
    serve(500);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    expect(await screen.findByText('Could not load this obligation')).toBeInTheDocument();
  });

  it('shows the loading state while the record is on its way', () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    expect(document.querySelector('[data-loading-state]')).toBeInTheDocument();
  });

  it('asks for the record and the register read together from the address, and mounts the register\'s parts once that read answers', async () => {
    const sent = serve(research);
    // Data stays fresh for 30 seconds, as in the app's own client (app/providers.tsx).
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: false } } });
    renderIn(<ObligationScreen obligationId="ob-1" />, undefined, client);
    // Before either answers, only the tags are mounted, asking for their list beside the
    // record: no register part is there yet to ask for what the register read is already
    // bringing, and every card is already in its place.
    expect(document.querySelector('[data-loading-state]')).toBeInTheDocument();
    expect(mounts()).toEqual(['Tags']);
    expect(cardTitles()).toEqual(CARDS);
    await waitFor(() => expect(mounts()).toEqual(['History', 'Handle', 'Gaps', 'Tags', 'Participants', 'Comments']));
    // The reports and related changes on the page came with the register read and asked nothing.
    await screen.findByText('No change affects this obligation');
    expect(new Set(sent.map((call) => call.path))).toEqual(new Set(['/api/v1/me', '/api/v1/obligations/ob-1', '/api/v1/obligations/ob-1/register']));
  });

  it('mounts the parts anyway when the register read fails, and each asks its own route', async () => {
    const sent = serve(research, 500);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await waitFor(() => expect(mounts()).toEqual(['History', 'Handle', 'Gaps', 'Tags', 'Participants', 'Comments']));
    expect(await screen.findByText('Does it apply to us could not be loaded')).toBeInTheDocument();
    // A part asking again does not take the others down with it: the read is asked a bounded number of times.
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(sent.filter((call) => call.path === '/api/v1/obligations/ob-1/register').length).toBeLessThanOrEqual(3);
    expect(mounts()).toHaveLength(6);
  });

  it('reads the record as of a typed date and offers the way back to today', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });
    expect(document.querySelector('[data-as-of]')).toBeNull();

    fireEvent.change(screen.getByLabelText('As of'), { target: { value: '2026-10-01' } });
    await waitFor(() => expect(document.querySelector('[data-as-of]')).toHaveAttribute('data-as-of', '2026-10-01'));
    expect(screen.getByText('Showing version 2, in force on 1 Oct 2026.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Version 2, from 1 Oct 2026' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Back to today' }));
    await waitFor(() => expect(document.querySelector('[data-as-of]')).toBeNull());
  });

  it('says so when no version of the record was in force on the date asked for', async () => {
    serve({ ...research, version: null, summary: null });
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });
    fireEvent.change(screen.getByLabelText('As of'), { target: { value: '2017-01-01' } });
    expect(await screen.findByText('No version of this obligation was in force on 1 Jan 2017.')).toBeInTheDocument();
  });

  it('marks the sentences a version added and names both effective dates', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });

    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    await waitFor(() => expect(document.querySelector('[data-diff-banner]')).toBeInTheDocument());
    expect(document.querySelector('[data-diff-banner]')).toHaveTextContent(
      'Comparing version 1 (in force since it began) with version 2 (in force from 1 Oct 2026).',
    );
    expect(document.querySelector('[data-diff-banner] [data-machine-confirmed]')).toBeNull();
    expect(document.querySelector('[data-legal-text] ins')?.textContent).toContain('The institution sets criteria for an annual assessment.');
    // Either side machine translated labels the whole comparison (INV-05).
    expect(document.querySelector('[data-summary] [data-machine-translation]')?.textContent).toBe('Machine-translated from Swedish');

    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    await waitFor(() => expect(document.querySelector('[data-diff-banner]')).toBeNull());
  });

  it('offers "This looks wrong" and the reported problems only to a reader who may report, and acknowledges the report', async () => {
    serve(research);
    const withoutReport = renderIn(<ObligationScreen obligationId="ob-1" />, ['library.read']);
    await screen.findByRole('heading', { level: 1, name: TITLE });
    await screen.findByText('No change affects this obligation');
    expect(screen.queryByRole('button', { name: 'This looks wrong' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Reported problems/ })).not.toBeInTheDocument();
    withoutReport.unmount();

    resetApiForTests();
    tokenStore.set('session-token');
    const sent = serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: TITLE });
    fireEvent.click(screen.getByRole('button', { name: 'This looks wrong' }));
    fireEvent.change(await screen.findByLabelText('What you see'), { target: { value: 'The English says annually.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }));
    expect(await screen.findByText('Report sent. Thank you.')).toBeInTheDocument();
    // What was on screen rides along: the version and the language being read.
    expect(sent.filter((call) => call.method === 'post' && call.path === '/api/v1/problem-reports').map((call) => call.body)).toEqual([
      { description: 'The English says annually.', language: 'en', versionNumber: 1, subjectType: 'obligation', subjectId: 'ob-1' },
    ]);
  });

  it('folds the record\'s reported problems with their count, and reads them again once a report is filed', async () => {
    const sent = serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    const fold = await screen.findByRole('button', { name: 'Reported problems (0)' });
    expect(fold).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(fold);
    expect((await screen.findByText('No problems reported on this record.')).closest('[data-problem-reports]')).not.toBeNull();
    const reads = () => sent.filter((call) => call.method === 'get' && call.path === '/api/v1/problem-reports');
    expect(new Set(reads().map((call) => JSON.stringify(call.params)))).toEqual(new Set([JSON.stringify({ subjectType: 'obligation', subjectId: 'ob-1', limit: 20, offset: 0 })]));
    const before = reads().length;

    fireEvent.click(screen.getByRole('button', { name: 'This looks wrong' }));
    fireEvent.change(await screen.findByLabelText('What you see'), { target: { value: 'The English says annually.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));
    await waitFor(() => expect(reads().length).toBeGreaterThan(before));
  });
});

describe('the diff sentence', () => {
  it('names a version by the date it took effect, or says it has been in force since the record began', () => {
    expect(effectiveIn(null, t, defaultFormatContext)).toBe('in force since it began');
    expect(effectiveIn({ date: '2026-10-01', precision: 'day' }, t, defaultFormatContext)).toBe('in force from 1 Oct 2026');
    // A legal date renders at its own precision, never as a day it does not claim.
    expect(effectiveIn({ date: '2026-10-01', precision: 'quarter' }, t, defaultFormatContext)).toBe('in force from Q4 2026');
    expect(diffSentence(versionDiff, t, defaultFormatContext)).toBe(
      'Comparing version 1 (in force since it began) with version 2 (in force from 1 Oct 2026).',
    );
  });
});

// Every stand-in above is a part its package filled and tests in its own file.
describe('the stand-ins', () => {
  it('cover parts that exist', async () => {
    for (const name of PANELS) {
      const file = name === 'Handle' ? './ObligationStatusPanel' : `./Obligation${name}Panel`;
      const actual = await vi.importActual<Record<string, unknown>>(file);
      expect(typeof actual[`Obligation${name}Panel`]).toBe('function');
    }
  });
});
