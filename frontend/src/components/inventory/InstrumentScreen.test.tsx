import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { InstrumentScreen } from './InstrumentScreen';
import type { RegisterInstrumentApplicability } from '@/features/register/api';
import type { InstrumentDetail, InstrumentLinkRef, Obligation, ProvisionNode } from '@/features/library/types';
import type { ProblemReport } from '@/features/library/problem-reports/types';

// The regulation's page (design/screens/tenant-instrument.html; INV-01, INV-06,
// INV-09, FP-03): the header pills, the obligations first with what applies rolled
// up, the answer filter, a search, the scope and a pager; a directive's national
// laws opened in place; the Identity panel with its reported problems folded,
// lineage as links, and every state the card names. Nothing here writes but
// "This looks wrong".

const fffs: InstrumentDetail = {
  id: 'in-1',
  stableKey: 'fffs-2017-2',
  shortName: 'FFFS 2017:2',
  name: { text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false },
  level: { key: 'authority_regulation', kind: null, label: 'Supervisory regulation' },
  binding: true,
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  authority: { key: 'fi', name: 'Finansinspektionen', shortName: 'FI', url: 'https://www.fi.se/' },
  regime: { key: 'securities', kind: null, label: 'Securities' },
  officialRef: 'FFFS 2017:2',
  eliUri: '',
  inForceFrom: { date: '2018-01-03', precision: 'day' },
  inForceTo: null,
  implementsNote: 'MiFID II delegated directive (EU) 2017/593',
  sourceUrl: 'https://www.fi.se/en/published/regulations/2017/fffs-20172/',
  lastVerifiedAt: '2026-06-30T07:12:44Z',
  verifiedBy: null,
  privateToUs: false,
  summary: null,
  nameTranslations: [{ text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false }],
  summaryTranslations: [],
  implements: [],
  implementedBy: [],
  obligationCounts: { inLibrary: 34, inScope: 34, waitingForReview: 0 },
  lineage: [
    {
      relation: { key: 'amends', kind: null, label: 'Amends' },
      direction: 'incoming',
      instrument: { id: 'in-11', key: 'fffs-2026-11', shortName: 'FFFS 2026:11' },
      note: 'Amends FFFS 2017:2, in force 1 October 2026.',
      fromRef: '',
      toRef: '',
    },
    {
      relation: { key: 'implements', kind: null, label: 'Implements' },
      direction: 'outgoing',
      instrument: { id: 'in-12', key: 'celex-32017l0593', shortName: 'Delegated directive (EU) 2017/593' },
      note: '',
      fromRef: '',
      toRef: '',
    },
  ],
};

const researchObligation: Obligation = {
  id: 'ob-1',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false },
  instrument: { id: 'in-1', key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
  bindingLevel: { key: 'authority_regulation', kind: null, label: 'Supervisory regulation' },
  binding: true,
  dutyType: { key: 'governance', kind: null, label: 'Governance' },
  tags: [],
  scope: [],
  version: { versionNumber: 1, effectiveFrom: null, approvedAt: null, verifiedOrigin: '', confirmedByAgent: null, proposedByAgent: null },
  upcomingVersion: null,
  jurisdiction: { key: 'se', kind: 'country', label: 'Sweden' },
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: null,
  verifiedBy: null,
  openChangeCount: 0,
  tenantTags: [],
  privateToUs: false,
  complianceStatus: null,
  applicability: 'under_assessment',
  firstLineOwner: null,
  ownerTeam: null,
};

/** The bank's answers over the regulation's 14 obligations in scope, in two companies. */
const rollup: RegisterInstrumentApplicability = {
  inScope: 14,
  underAssessment: 5,
  applies: 8,
  notApplicable: 1,
  statuses: [
    { status: { key: 'compliant', kind: 'compliant', label: 'Compliant' }, count: 5 },
    { status: { key: 'partly_compliant', kind: 'partly', label: 'Partly compliant' }, count: 2 },
    { status: { key: 'gap', kind: 'gap', label: 'Gap' }, count: 1 },
  ],
  companies: [
    { orgUnit: { id: 'ou-1', name: 'Example Bank AB' }, offered: 12, applies: 8, notApplicable: 1, underAssessment: 3, toDecide: 2 },
    { orgUnit: { id: 'ou-2', name: 'Example Fonder AB' }, offered: 12, applies: 0, notApplicable: 0, underAssessment: 12, toDecide: 12 },
  ],
};

const chapter: ProvisionNode = {
  id: 'pr-9',
  stableKey: 'fffs-2017-2/9',
  kind: { key: 'chapter', kind: 'division', label: 'Chapter' },
  refLabel: '9 kap.',
  heading: 'Skydd för investerare',
  path: 'FFFS 2017:2 > 9 kap.',
  children: [],
  versions: [],
  inForceVersion: null,
  obligations: [],
};

const ME = {
  user: { id: 'u1', name: 'Sara', locale: 'en' },
  tenant: { timezone: 'Europe/Stockholm' },
  permissions: ['library.read', 'problems.report'],
  enrolmentPending: false,
};

const REGISTER_READER = ['library.read', 'problems.report', 'register.read'];

function renderIn(node: ReactNode, permissions: string[] = ['library.read', 'problems.report'], locale: 'en' | 'sv' = 'en') {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      {
        <LocaleProvider locale={locale}>
          <PermissionsProvider permissions={permissions}>{node}</PermissionsProvider>
        </LocaleProvider>
      }
    </Wrapper>,
  );
}

interface Serving {
  /** The obligations of each regulation by stable key, where a page reads more than one. */
  byInstrument?: Record<string, Obligation[]>;
  /** Each regulation's total beyond its page, by stable key. */
  totalByInstrument?: Record<string, number>;
  provisions?: ProvisionNode[];
  reports?: unknown[];
}

/** The server: /me, the card, its obligations (`total` beyond the page when given), the roll-up and the report. */
function serve(answer: InstrumentDetail | number, obligations: Obligation[] = [researchObligation], total = obligations.length, serving: Serving = {}) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/obligations') {
      const key = (sent.params as { instrument?: string }).instrument ?? '';
      const items = serving.byInstrument?.[key] ?? obligations;
      return { status: 200, data: { items, total: serving.byInstrument === undefined ? total : (serving.totalByInstrument?.[key] ?? items.length) } };
    }
    if (sent.path.endsWith('/provisions')) return { status: 200, data: serving.provisions ?? [] };
    if (sent.path.endsWith('/applicability')) return { status: 200, data: rollup };
    // The record's "Reported problems" (AUD-03): none unless the test files some.
    if (sent.method === 'get' && sent.path === '/api/v1/problem-reports') return { status: 200, data: { items: serving.reports ?? [], total: serving.reports?.length ?? 0 } };
    if (sent.method === 'post' && sent.path === '/api/v1/problem-reports') return { status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } };
    if (typeof answer === 'number') return { status: answer, data: { detail: 'no', code: answer === 404 ? 'not_found' : 'server_error' } };
    return { status: 200, data: answer };
  }, { me: ME });
}

const listReads = (sent: Sent[]) => sent.filter((s) => s.path === '/api/v1/obligations');
const lastList = (sent: Sent[]) => listReads(sent).at(-1)?.params;

function panel(): HTMLElement {
  return document.querySelector('[data-obligations-panel]') as HTMLElement;
}

/** The obligations panel once the regulation has loaded. */
async function loaded(): Promise<HTMLElement> {
  await screen.findByRole('heading', { level: 1 });
  return panel();
}

describe('InstrumentScreen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('a standard reads "Standard" in its binding slots and says its text is licensed, with the catalogue link', async () => {
    const iso: InstrumentDetail = {
      ...fffs,
      stableKey: 'iso-27001-2022',
      shortName: 'ISO/IEC 27001:2022',
      name: { text: 'Information security management systems', language: 'en', isOriginal: true, isMachine: false },
      level: { key: 'standard', kind: 'standard', label: 'Standard edition' },
      binding: false,
      jurisdiction: { key: 'int', kind: 'international', label: 'International' },
      authority: null,
      regime: { key: 'ai_ict', kind: null, label: 'AI and ICT' },
      sourceUrl: 'https://www.iso.org/standard/27001',
      lineage: [],
    };
    const control: Obligation = {
      ...researchObligation,
      instrument: { id: iso.id, key: iso.stableKey, shortName: iso.shortName },
      bindingLevel: iso.level,
      binding: false,
    };
    const sent = serve(iso, [control]);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1, name: 'ISO/IEC 27001:2022' });
    expect(screen.getByText('Information security management systems')).toBeVisible();

    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['Standard edition', 'information'],
      ['Standard', 'information'],
      ['International', 'brand'],
      ['AI and ICT', 'information'],
    ]);
    expect(screen.queryByText('Guidance, comply or explain')).toBeNull();
    const identity = document.querySelector('[data-identity-panel]') as HTMLElement;
    expect(within(identity).getByText('Standard')).toBeInTheDocument();

    const licensed = document.querySelector('[data-provision-tree] [data-provisions-licensed]') as HTMLElement;
    expect(within(licensed).getByRole('link', { name: "See it in the publisher's catalogue" })).toHaveAttribute('href', iso.sourceUrl);
    expect(sent.some((request) => request.path.endsWith('/provisions'))).toBe(false);

    // The row of an obligation under it reads "Standard" in its guidance slot, never "Guidance".
    await waitFor(() => expect(document.querySelector('[data-obligations-panel] [data-obligation]')).not.toBeNull());
    const row = document.querySelector('[data-obligations-panel] [data-obligation]') as HTMLElement;
    expect([...row.querySelectorAll('[data-pill]')].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['ISO/IEC 27001:2022', 'brand'],
      ['Standard', 'information'],
    ]);
  });

  it('leads the head of the bank\'s own instrument with "Private to us", its short name outlined (OWN-04)', async () => {
    serve({ ...fffs, privateToUs: true });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1, name: 'FFFS 2017:2' });
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].slice(0, 2).map((pill) => [pill.textContent, pill.getAttribute('data-pill'), pill.hasAttribute('data-outlined')])).toEqual([
      ['Private to us', 'information', true],
      ['Supervisory regulation', 'information', false],
    ]);
  });

  it('shows the header pills, the identity panel, the source link and the obligations from this instrument', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1, name: 'FFFS 2017:2' });

    // The short name is the heading and the official title stands under it; the jurisdiction
    // is brand, level and binding are information (INV-S1).
    expect(screen.getByText('FFFS 2017:2 om värdepappersrörelse')).toBeVisible();
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['Supervisory regulation', 'information'],
      ['Binding', 'information'],
      ['Sweden', 'brand'],
      ['Securities', 'information'],
    ]);

    const identity = document.querySelector('[data-identity-panel]') as HTMLElement;
    expect(within(identity).getByText('FFFS 2017:2')).toBeInTheDocument();
    expect(within(identity).getByText('Not available')).toBeInTheDocument();
    expect(within(identity).getByText('Finansinspektionen')).toBeInTheDocument();
    expect(document.querySelector('[data-last-verified]')?.textContent).toBe('30 Jun 2026');

    const source = screen.getByRole('link', { name: 'Source' });
    expect(source).toHaveAttribute('href', fffs.sourceUrl);
    expect(source).toHaveAttribute('rel', 'noopener noreferrer');

    expect(await screen.findByText('Pay for third-party research only under the permitted models')).toBeInTheDocument();
    // No provision text held: the panel is left out rather than promising text.
    expect(document.querySelector('[data-provision-tree]')).toBeNull();
  });

  it('goes back to the Regulations tab of the inventory', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('link', { name: '← Regulations' })).toHaveAttribute('href', '/inventory?tab=instruments');
  });

  it('puts the obligations first and the provisions under them, with what it is, its identity and lineage beside them', async () => {
    serve(
      {
        ...fffs,
        summary: { text: "Finansinspektionen's rules for investment services.", language: 'en', isOriginal: true, isMachine: false },
        summaryTranslations: [{ text: "Finansinspektionen's rules for investment services.", language: 'en', isOriginal: true, isMachine: false }],
      },
      [researchObligation],
      1,
      { provisions: [chapter] },
    );
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await waitFor(() => expect(document.querySelector('[data-provision-tree]')).not.toBeNull());
    const order = ['[data-obligations-panel]', '[data-provision-tree]', '[data-summary-panel]', '[data-identity-panel]', '[data-lineage-panel]'];
    const nodes = order.map((selector) => document.querySelector(selector) as HTMLElement);
    nodes.slice(1).forEach((node, i) => expect((nodes[i] as HTMLElement).compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy());
    // Obligations and provisions share the wide column; the other three the narrow one.
    expect(nodes[0]?.parentElement).toBe(nodes[1]?.parentElement);
    expect(nodes[2]?.parentElement).toBe(nodes[4]?.parentElement);
    expect(nodes[0]?.parentElement).not.toBe(nodes[2]?.parentElement);
  });

  it('groups the lineage by relation and direction, each related regulation a link to its page', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    const groups = [...document.querySelectorAll('[data-lineage-group]')];
    expect(groups.map((group) => [group.getAttribute('data-lineage-group'), group.querySelector('h3')?.textContent])).toEqual([
      ['amends:incoming', 'Amends this regulation'],
      ['implements:outgoing', 'Implements'],
    ]);
    const amendedBy = document.querySelector('[data-lineage-group="amends:incoming"]') as HTMLElement;
    expect(within(amendedBy).getByRole('link', { name: 'FFFS 2026:11' })).toHaveAttribute('href', '/inventory/instruments/in-11');
    expect(within(amendedBy).getByText('Amends FFFS 2017:2, in force 1 October 2026.')).toBeInTheDocument();
    const implementing = document.querySelector('[data-lineage-group="implements:outgoing"] [data-lineage-instrument="celex-32017l0593"]') as HTMLElement;
    expect(within(implementing).getByRole('link', { name: 'Delegated directive (EU) 2017/593' })).toHaveAttribute('href', '/inventory/instruments/in-12');
  });

  it('shows what implements this instrument and what it amends, pairs no fixed list names', async () => {
    // The directive's card sees FFFS 2017:2 implementing it (incoming implements);
    // the amending instrument's card sees its own amendment going out.
    const lineage: InstrumentDetail['lineage'] = [
      { relation: { key: 'implements', kind: null, label: 'Implements' }, direction: 'incoming', instrument: { id: 'in-1', key: 'fffs-2017-2', shortName: 'FFFS 2017:2' }, note: '', fromRef: '', toRef: '' },
      { relation: { key: 'amends', kind: null, label: 'Amends' }, direction: 'outgoing', instrument: { id: 'in-3', key: 'fffs-2017-1', shortName: 'FFFS 2017:1' }, note: '', fromRef: '', toRef: '9 kap. 6 §' },
    ];
    serve({ ...fffs, lineage });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    const implementedBy = document.querySelector('[data-lineage-group="implements:incoming"]') as HTMLElement;
    expect(within(implementedBy).getByRole('heading', { level: 3 })).toHaveTextContent('Implements this regulation');
    expect(within(implementedBy).getByText('FFFS 2017:2')).toBeInTheDocument();
    const amends = document.querySelector('[data-lineage-group="amends:outgoing"]') as HTMLElement;
    expect(within(amends).getByRole('heading', { level: 3 })).toHaveTextContent('Amends');
    expect(within(amends).getByText('FFFS 2017:1')).toBeInTheDocument();
  });

  it('leaves the lineage out when the instrument has none', async () => {
    serve({ ...fffs, lineage: [] });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    expect(document.querySelector('[data-lineage-panel]')).toBeNull();
  });

  it('says what the instrument is, and how many of its obligations the library holds and our scope takes', async () => {
    serve({
      ...fffs,
      summary: { text: "Finansinspektionen's rules for investment services.", language: 'en', isOriginal: true, isMachine: false },
      summaryTranslations: [{ text: "Finansinspektionen's rules for investment services.", language: 'en', isOriginal: true, isMachine: false }],
      obligationCounts: { inLibrary: 5, inScope: 3, waitingForReview: 2 },
    });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    const summary = (await screen.findByText("Finansinspektionen's rules for investment services.")).closest('[data-summary-panel]') as HTMLElement;
    expect(within(summary).getByRole('heading', { name: 'What it is' })).toBeInTheDocument();
    expect(within(panel()).getByRole('heading', { name: 'Obligations from these rules' })).toBeInTheDocument();
    expect(panel().querySelector('[data-applies-counts]')).toHaveTextContent('5 obligations in the library. 3 fall in your scope.');
    expect(panel().querySelector('[data-applies-waiting]')).toHaveTextContent('2 more obligations wait for review before reaching the library.');
  });

  describe('in the languages the library holds', () => {
    const swedishName = { text: 'FFFS 2017:2 om värdepappersrörelse', language: 'sv', isOriginal: true, isMachine: false };
    const englishName = { text: 'FFFS 2017:2 on securities business', language: 'en', isOriginal: false, isMachine: true };
    const swedish = { text: 'Finansinspektionens regler om värdepappersrörelse.', language: 'sv', isOriginal: true, isMachine: false };
    const english = { text: "Finansinspektionen's rules on securities business.", language: 'en', isOriginal: false, isMachine: true };
    const chips = (summary: HTMLElement) => within(summary.querySelector('[data-language-chips]') as HTMLElement).getAllByRole('button').map((chip) => chip.textContent);

    it("names the summary's languages only, labels its machine translation as the obligation page does, and follows it with the name", async () => {
      serve({ ...fffs, name: englishName, nameTranslations: [swedishName, englishName], summary: english, summaryTranslations: [swedish, english] });
      renderIn(<InstrumentScreen instrumentId="in-1" />);
      const summary = (await screen.findByText(english.text)).closest('[data-summary-panel]') as HTMLElement;
      // The summary is bleqq's wording: no language of it is the original.
      expect(chips(summary)).toEqual(['Swedish', 'English']);
      expect(summary).not.toHaveTextContent(/original/i);
      expect(summary.querySelector('[data-machine-translation]')).toHaveTextContent('Machine-translated from Swedish');
      // An English reader has no name of the authority's own in English: the machine's, labelled.
      expect(document.querySelector('[data-name-machine]')).toHaveTextContent('Name machine-translated from Swedish');
      expect(screen.getByText(englishName.text)).toBeInTheDocument();

      fireEvent.click(within(summary).getByRole('button', { name: 'Swedish' }));

      expect(within(summary).getByText(swedish.text)).toHaveAttribute('lang', 'sv');
      expect(summary.querySelector('[data-machine-translation]')).toBeNull();
      expect(screen.getByText(swedishName.text)).toBeInTheDocument();
      expect(document.querySelector('[data-name-machine]')).toBeNull();
    });

    it("gives a Swedish reader the authority's Swedish name, not the machine's English one, when the summary is held in English only", async () => {
      const englishOnly = { text: "Finansinspektionen's rules on securities business.", language: 'en', isOriginal: true, isMachine: false };
      serve({ ...fffs, name: swedishName, nameTranslations: [swedishName, englishName], summary: englishOnly, summaryTranslations: [englishOnly] });
      renderIn(<InstrumentScreen instrumentId="in-1" />, ['library.read', 'problems.report'], 'sv');
      const summary = (await screen.findByText(englishOnly.text)).closest('[data-summary-panel]') as HTMLElement;
      expect(screen.getByText(swedishName.text)).toBeInTheDocument();
      expect(screen.queryByText(englishName.text)).toBeNull();
      expect(document.querySelector('[data-name-machine]')).toBeNull();
      // The summary's own language and the reader's, by name only.
      expect(chips(summary)).toEqual(['engelska', 'svenska']);

      // The reader's language, not held: says so and offers the language it is written in.
      fireEvent.click(within(summary).getByRole('button', { name: 'svenska' }));
      expect(within(summary).getByText('Ingen text på svenska ännu')).toBeVisible();
      fireEvent.click(within(summary).getByRole('link', { name: 'Läs den på engelska' }));
      expect(within(summary).getByText(englishOnly.text)).toHaveAttribute('lang', 'en');
    });
  });

  describe('a directive', () => {
    const law = (id: string, key: string, shortName: string, jurisdiction: string, label: string, inLibrary: number, inScope: number): InstrumentLinkRef => ({
      id,
      key,
      shortName,
      jurisdiction: { key: jurisdiction, kind: 'country', label },
      obligationCounts: { inLibrary, inScope },
    });
    const kapitalmarkedsloven = law('in-20', 'dk-lov-2017-650', 'Kapitalmarkedsloven', 'dk', 'Denmark', 21, 0);
    const lvm = law('in-21', 'sfs-2007-528', 'LVM', 'se', 'Sweden', 34, 23);
    const mifid: InstrumentDetail = {
      ...fffs,
      id: 'in-9',
      stableKey: 'celex-32014l0065',
      shortName: 'MiFID II',
      level: { key: 'eu_directive', kind: null, label: 'EU directive' },
      jurisdiction: { key: 'eu', kind: 'union', label: 'European Union' },
      lineage: [],
      obligationCounts: { inLibrary: 0, inScope: 0, waitingForReview: 0 },
      // The read answers the laws in its own order; the page opens those in scope first.
      implementedBy: [kapitalmarkedsloven, lvm],
    };
    const lvmDuty: Obligation = { ...researchObligation, id: 'ob-21', stableKey: 'obl-lvm-governance', instrument: { id: 'in-21', key: 'sfs-2007-528', shortName: 'LVM' } };

    it('says its obligations come from national law, with the totals over the laws the library holds', async () => {
      serve(mifid, [], 0, { byInstrument: { 'sfs-2007-528': [lvmDuty], 'dk-lov-2017-650': [] } });
      renderIn(<InstrumentScreen instrumentId="in-9" />);
      const directive = (await screen.findByRole('heading', { name: 'Obligations from this directive' })).closest('[data-obligations-panel]') as HTMLElement;
      expect(directive).toHaveTextContent("A directive binds the member states, not your bank directly. A bank's obligations come from each country's law that implements it.");
      expect(directive.querySelector('[data-national-totals]')).toHaveTextContent('55 obligations in 2 national laws the library holds. 23 fall in your scope.');
      // No scope control and no search over a list that cannot have rows of its own.
      expect(within(directive).queryByRole('button', { name: 'My scope' })).toBeNull();
      expect(within(directive).queryByLabelText('Find an obligation')).toBeNull();
    });

    it('opens the laws with obligations in scope first and reads only an open law', async () => {
      const sent = serve(mifid, [], 0, { byInstrument: { 'sfs-2007-528': [lvmDuty], 'dk-lov-2017-650': [] }, totalByInstrument: { 'sfs-2007-528': 23 } });
      renderIn(<InstrumentScreen instrumentId="in-9" />);
      await screen.findByRole('heading', { name: 'Obligations from this directive' });
      const swedish = document.querySelector('[data-national-law="sfs-2007-528"]') as HTMLElement;
      const laws = [...document.querySelectorAll('[data-national-law]')].map((fold) => fold.getAttribute('data-national-law'));
      expect(laws).toEqual(['sfs-2007-528', 'dk-lov-2017-650']);

      // The Swedish law holds duties in scope: open, its first page read for it alone, each a row.
      const swedishToggle = within(swedish).getByRole('button', { name: /LVM/ });
      expect(swedishToggle).toHaveAttribute('aria-expanded', 'true');
      expect(swedishToggle).toHaveTextContent('Sweden · 34 obligations · 23 in your scope');
      expect(await within(swedish).findByText('Pay for third-party research only under the permitted models')).toBeInTheDocument();
      // Its page opens on the bank's scope, so the link counts what it lists there, and the
      // first page says it is only the first.
      expect(swedish.querySelector('[data-first-of]')).toHaveTextContent('First 1 of 23 in your scope');
      expect(within(swedish).getByRole('link', { name: 'See all 23 in your scope' })).toHaveAttribute('href', '/inventory/instruments/in-21');
      expect(listReads(sent).map((s) => s.params)).toEqual([{ instrument: 'sfs-2007-528', limit: 20, offset: 0 }]);

      // The Danish law has none in scope: closed, and unread until it is opened.
      const danish = document.querySelector('[data-national-law="dk-lov-2017-650"]') as HTMLElement;
      const danishToggle = within(danish).getByRole('button', { name: /Kapitalmarkedsloven/ });
      expect(danishToggle).toHaveAttribute('aria-expanded', 'false');
      // A closed law's page is one click away: its name is a link outside the toggle.
      expect(within(danish).getByRole('link', { name: 'Kapitalmarkedsloven' })).toHaveAttribute('href', '/inventory/instruments/in-20');
      expect(listReads(sent)).toHaveLength(1);
      expect(danishToggle).toHaveTextContent('Denmark · 21 obligations · 0 in your scope');
      fireEvent.click(danishToggle);
      expect(await within(danish).findByText('No obligation from this regulation is in our scope.')).toBeVisible();
      expect(danish.querySelector('[data-first-of]')).toBeNull();
      expect(within(danish).getByRole('link', { name: 'Open this law' })).toHaveAttribute('href', '/inventory/instruments/in-20');
      expect(lastList(sent)).toEqual({ instrument: 'dk-lov-2017-650', limit: 20, offset: 0 });
    });

    it('says when the library holds no national law that implements it', async () => {
      serve({ ...mifid, implementedBy: [] }, []);
      renderIn(<InstrumentScreen instrumentId="in-9" />);
      expect(await screen.findByText('The library holds no national law that implements it yet.')).toBeVisible();
      expect(document.querySelector('[data-national-totals]')).toBeNull();
    });
  });

  it('says when the library holds no obligation under it, or that new ones wait for review', async () => {
    serve({ ...fffs, level: { key: 'act', kind: null, label: 'Act' }, obligationCounts: { inLibrary: 0, inScope: 0, waitingForReview: 0 } }, []);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('The library holds no obligation under it yet.')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Obligations from this act' })).toBeInTheDocument();

    serve({ ...fffs, obligationCounts: { inLibrary: 0, inScope: 0, waitingForReview: 1 } }, []);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('1 more obligation waits for review before reaching the library.')).toBeVisible();
  });

  it('lists what the instrument implements, each opening its own card', async () => {
    serve({ ...fffs, lineage: [], implements: [{ id: 'in-7', key: 'celex-32014l0065', shortName: 'MiFID II', jurisdiction: { key: 'eu', kind: 'union', label: 'European Union' }, obligationCounts: { inLibrary: 0, inScope: 0 } }] });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    const implementsGroup = (await screen.findByRole('link', { name: 'MiFID II' })).closest('[data-implements]') as HTMLElement;
    expect(within(implementsGroup).getByRole('heading', { level: 3 })).toHaveTextContent('Implements');
    expect(within(implementsGroup).getByRole('link', { name: 'MiFID II' })).toHaveAttribute('href', '/inventory/instruments/in-7');
  });

  it('reads the obligations inside our scope first, with the total and a link to the same list in the inventory', async () => {
    const sent = serve(fffs, [researchObligation], 34);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    expect(listReads(sent)[0]?.params).toEqual({ instrument: 'fffs-2017-2', limit: 20, offset: 0 });
    expect(within(panel()).getByRole('button', { name: 'My scope' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(panel()).getByRole('button', { name: 'Show all items' })).toHaveAttribute('aria-pressed', 'false');
    expect(panel().querySelector('[data-obligations-total]')).toHaveTextContent('34 obligations');
    expect(within(panel()).getByRole('link', { name: 'Open in the inventory' })).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2');
  });

  it('pages the list 20 at a time with the inventory\'s pager', async () => {
    const sent = serve(fffs, [researchObligation], 34);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    const pager = panel().querySelector('[data-list-pager]') as HTMLElement;
    expect(pager.querySelector('[data-pager-range]')).toHaveTextContent('of 34');
    fireEvent.click(within(pager).getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(lastList(sent)).toEqual({ instrument: 'fffs-2017-2', limit: 20, offset: 20 }));
  });

  it('finds an obligation by the words typed on Enter, never per key, and starts again at the first page', async () => {
    const sent = serve(fffs, [researchObligation], 34);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    fireEvent.click(within(panel().querySelector('[data-list-pager]') as HTMLElement).getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(lastList(sent)).toMatchObject({ offset: 20 }));
    const field = within(panel()).getByLabelText('Find an obligation');
    const reads = listReads(sent).length;
    fireEvent.change(field, { target: { value: ' res' } });
    fireEvent.change(field, { target: { value: ' research ' } });
    // Typing reads nothing and keeps the rows on screen.
    expect(listReads(sent)).toHaveLength(reads);
    expect(screen.getByText('Pay for third-party research only under the permitted models')).toBeVisible();
    fireEvent.submit(within(panel()).getByRole('search'));
    await waitFor(() => expect(lastList(sent)).toEqual({ instrument: 'fffs-2017-2', q: 'research', limit: 20, offset: 0 }));
    // Emptied, the search clears at once.
    fireEvent.change(field, { target: { value: '' } });
    await waitFor(() => expect(lastList(sent)).toEqual({ instrument: 'fffs-2017-2', limit: 20, offset: 0 }));
  });

  it('asks for the obligations outside our scope on request, and the link follows', async () => {
    const sent = serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    fireEvent.click(within(panel()).getByRole('button', { name: 'Show all items' }));
    await waitFor(() => expect(lastList(sent)).toMatchObject({ instrument: 'fffs-2017-2', footprint: 'all' }));
    expect(within(panel()).getByRole('button', { name: 'Show all items' })).toHaveAttribute('aria-pressed', 'true');
    expect(await within(panel()).findByRole('link', { name: 'Open in the inventory' })).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2&scope=all');
  });

  it('asks for what the watched markets add, names each row\'s market, and the link follows', async () => {
    const sent = serve(fffs, [{ ...researchObligation, inFootprint: false, jurisdiction: { key: 'dk', kind: 'country', label: 'Denmark' } }]);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    fireEvent.click(within(panel()).getByRole('button', { name: 'Markets we watch' }));
    await waitFor(() => expect(lastList(sent)).toMatchObject({ instrument: 'fffs-2017-2', footprint: 'watched' }));
    expect(await within(panel()).findByText('Market we watch: Denmark')).toBeVisible();
    expect(panel().querySelector('[data-outside-footprint]')).toBeNull();
    expect(within(panel()).getByRole('link', { name: 'Open in the inventory' })).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2&scope=watched');
  });

  describe('what applies, for a reader of the register', () => {
    it('rolls up the answers, where it applies how we comply, and each company with what is left to decide', async () => {
      const sent = serve(fffs, [researchObligation], 34);
      renderIn(<InstrumentScreen instrumentId="in-1" />, REGISTER_READER);
      const filter = await within(await loaded()).findByRole('group', { name: 'Filter by answer' });
      expect(sent.filter((s) => s.path === '/api/v1/instruments/in-1/applicability')).toHaveLength(1);
      expect(within(filter).getAllByRole('button').map((chip) => [chip.textContent, chip.getAttribute('aria-pressed')])).toEqual([
        ['All 14', 'true'],
        ['To decide 5', 'false'],
        ['Applies 8', 'false'],
        ['Does not apply 1', 'false'],
      ]);

      // Each status takes the tone of its kind, never one a screen picks.
      const where = panel().querySelector('[data-where-it-applies]') as HTMLElement;
      expect(where).toHaveTextContent('Where it applies5 Compliant2 Partly compliant1 Gap');
      const tones = [...where.querySelectorAll('[data-status] i')].map((dot) => (dot as HTMLElement).style.background);
      expect(tones[0]).toContain('positive');
      expect(tones[1]).toContain('warning');
      expect(tones[2]).toContain('negative');

      const byCompany = panel().querySelector('[data-by-company]') as HTMLElement;
      fireEvent.click(within(byCompany).getByRole('button', { name: 'By company' }));
      const bank = byCompany.querySelector('[data-company="ou-1"]') as HTMLElement;
      expect(bank).toHaveTextContent('Example Bank AB8 apply · 1 does not · 2 to decide');
      expect(within(bank).getByRole('link', { name: 'Decide 2' })).toHaveAttribute('href', '/applies?company=ou-1&instrument=fffs-2017-2');
      const funds = byCompany.querySelector('[data-company="ou-2"]') as HTMLElement;
      expect(within(funds).getByRole('link', { name: 'Decide 12' })).toHaveAttribute('href', '/applies?company=ou-2&instrument=fffs-2017-2');
    });

    it('filters the list by each answer, and the inventory link carries the answer chosen', async () => {
      const sent = serve(fffs, [researchObligation], 34);
      renderIn(<InstrumentScreen instrumentId="in-1" />, REGISTER_READER);
      const filter = await within(await loaded()).findByRole('group', { name: 'Filter by answer' });
      const chip = (name: string) => within(filter).getByRole('button', { name });
      const inventory = () => within(panel()).getByRole('link', { name: 'Open in the inventory' });

      fireEvent.click(chip('To decide 5'));
      await waitFor(() => expect(lastList(sent)).toEqual({ instrument: 'fffs-2017-2', applicability: 'under_assessment', limit: 20, offset: 0 }));
      expect(chip('To decide 5')).toHaveAttribute('aria-pressed', 'true');
      await waitFor(() => expect(inventory()).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2&applicability=under_assessment'));
      fireEvent.click(chip('Applies 8'));
      await waitFor(() => expect(lastList(sent)).toMatchObject({ applicability: 'applies' }));
      fireEvent.click(chip('Does not apply 1'));
      await waitFor(() => expect(lastList(sent)).toMatchObject({ applicability: 'not_applicable' }));
      fireEvent.click(chip('All 14'));
      await waitFor(() => expect(lastList(sent)).toEqual({ instrument: 'fffs-2017-2', limit: 20, offset: 0 }));
      await waitFor(() => expect(inventory()).toHaveAttribute('href', '/inventory?instrument=fffs-2017-2'));
    });

    it('counts what is in scope only, so it leaves with the scope and takes its answer filter along', async () => {
      const sent = serve(fffs, [researchObligation], 34);
      renderIn(<InstrumentScreen instrumentId="in-1" />, REGISTER_READER);
      const filter = await within(await loaded()).findByRole('group', { name: 'Filter by answer' });
      fireEvent.click(within(filter).getByRole('button', { name: 'Applies 8' }));
      await waitFor(() => expect(lastList(sent)).toMatchObject({ applicability: 'applies' }));

      fireEvent.click(within(panel()).getByRole('button', { name: 'Show all items' }));
      await waitFor(() => expect(lastList(sent)).toEqual({ instrument: 'fffs-2017-2', footprint: 'all', limit: 20, offset: 0 }));
      expect(panel().querySelector('[data-rollup]')).toBeNull();

      fireEvent.click(within(panel()).getByRole('button', { name: 'My scope' }));
      const back = await within(panel()).findByRole('group', { name: 'Filter by answer' });
      expect(within(back).getByRole('button', { name: 'All 14' })).toHaveAttribute('aria-pressed', 'true');
    });

    it('says when nothing matches the answer chosen', async () => {
      serve(fffs, [], 0);
      renderIn(<InstrumentScreen instrumentId="in-1" />, REGISTER_READER);
      const filter = await within(await loaded()).findByRole('group', { name: 'Filter by answer' });
      fireEvent.click(within(filter).getByRole('button', { name: 'Applies 8' }));
      expect(await within(panel()).findByText('No obligation matches. Clear the search or choose All.')).toBeVisible();
    });

    it('leaves the companies out for a bank of one', async () => {
      const one = { ...rollup, companies: rollup.companies.slice(0, 1) };
      installAdapter(
        (sent) => {
          if (sent.path === '/api/v1/obligations') return { status: 200, data: { items: [researchObligation], total: 1 } };
          if (sent.path.endsWith('/applicability')) return { status: 200, data: one };
          if (sent.path.endsWith('/provisions')) return { status: 200, data: [] };
          if (sent.path === '/api/v1/problem-reports') return { status: 200, data: { items: [], total: 0 } };
          return { status: 200, data: fffs };
        },
        { me: ME },
      );
      renderIn(<InstrumentScreen instrumentId="in-1" />, REGISTER_READER);
      await within(await loaded()).findByRole('group', { name: 'Filter by answer' });
      expect(panel().querySelector('[data-by-company]')).toBeNull();
    });

    it('shows none of it, and asks for none of it, without register.read', async () => {
      const sent = serve(fffs, [researchObligation], 34);
      renderIn(<InstrumentScreen instrumentId="in-1" />);
      await screen.findByText('Pay for third-party research only under the permitted models');
      expect(sent.some((s) => s.path.endsWith('/applicability'))).toBe(false);
      expect(panel().querySelector('[data-rollup]')).toBeNull();
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  it('shows the ELI when the instrument carries one, and "by <name>" when someone verified it', async () => {
    serve({ ...fffs, eliUri: 'http://data.europa.eu/eli/reg/2017/565', verifiedBy: { id: 'u-2', name: 'Johan Ek' } });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('http://data.europa.eu/eli/reg/2017/565')).toBeInTheDocument();
    expect(document.querySelector('[data-last-verified]')?.textContent).toBe('30 Jun 2026 by Johan Ek');
  });

  it('says none is in our scope, and none at all once the reader looks outside it', async () => {
    serve(fffs, []);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('No obligation from this regulation is in our scope.')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Open in the inventory' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show all items' }));
    expect(await screen.findByText('This regulation has no obligation yet.')).toBeVisible();
  });

  it('offers a retry when the read fails, and Not found on a 404', async () => {
    const sent = serve(500);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/instruments/in-1').length).toBeGreaterThan(1));
    expect(screen.getByText('Could not load this regulation')).toBeVisible();

    serve(404);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByRole('heading', { name: 'Not found' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Regulations' })).toHaveAttribute('href', '/inventory?tab=instruments');
  });

  it('files a report through "This looks wrong", and hides the button without the permission', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'This looks wrong' }));
    fireEvent.change(screen.getByLabelText('What you see'), { target: { value: 'The in-force date looks wrong.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }));
    expect(await screen.findByText('Report sent. Thank you.')).toBeVisible();

    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />, ['library.read']);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('button', { name: 'This looks wrong' })).toBeNull();
  });

  it("folds the instrument's reported problems under Identity with their count, and leaves them out when there are none", async () => {
    const report: ProblemReport = {
      id: 'rep-1',
      subjectType: 'instrument',
      subjectId: fffs.id,
      subjectTitle: 'FFFS 2017:2',
      subjectReference: 'FFFS 2017:2',
      description: 'The in-force date does not match the source.',
      versionNumber: null,
      language: null,
      reporter: { id: 'u1', name: 'Sara' },
      status: 'open',
      createdAt: '2026-09-21T09:00:00Z',
      closedBy: null,
      closedAt: null,
      resolutionNote: null,
    };
    const sent = serve(fffs, [researchObligation], 1, { reports: [report] });
    const withReport = renderIn(<InstrumentScreen instrumentId="in-1" />);
    const identity = (await screen.findByRole('heading', { name: 'Identity' })).closest('[data-identity-panel]') as HTMLElement;
    const toggle = await within(identity).findByRole('button', { name: 'Reported problems (1)' });
    expect(within(identity).getByRole('button', { name: 'This looks wrong' })).toBeVisible();
    fireEvent.click(toggle);
    expect(await within(identity).findByText('The in-force date does not match the source.')).toBeVisible();
    // The fold and the section inside it read the same page of the record's reports.
    const reads = sent.filter((call) => call.method === 'get' && call.path === '/api/v1/problem-reports').map((call) => call.params);
    expect(new Set(reads.map((params) => JSON.stringify(params)))).toEqual(new Set([JSON.stringify({ subjectType: 'instrument', subjectId: fffs.id, limit: 20, offset: 0 })]));
    withReport.unmount();

    serve(fffs);
    const none = renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByText('Pay for third-party research only under the permitted models');
    expect(screen.queryByRole('button', { name: /Reported problems/ })).toBeNull();
    none.unmount();

    const unread = serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />, ['library.read']);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('button', { name: /Reported problems/ })).toBeNull();
    expect(unread.some((call) => call.path === '/api/v1/problem-reports')).toBe(false);
  });
});
