import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ObligationScreen, diffSentence, effectiveIn, languageChoices, originalLanguage, textIn } from './ObligationScreen';
import type { LocalizedText, ObligationDetail, ObligationVersionRow, VersionDiff } from '@/features/library/types';
import { defaultFormatContext } from '@/shared/utils/format';

// The obligation card (design/screens/tenant-obligation.html): the header
// slots in order, the summary in one language with the machine label, the
// scope and duty panels, provenance with "Last verified", and every state the
// card names. Nothing here writes, and nothing claims the duty applies here.

const t = createT('en');

const sv: LocalizedText = { text: 'Investeringsanalys från tredje part får tas emot endast…', language: 'sv', isOriginal: true, isMachine: false };
const en: LocalizedText = { text: 'Research from third parties may be received only if…', language: 'en', isOriginal: false, isMachine: true };

// Version 1 was seeded, so nobody approved it; version 2 a person approved.
// Every instant is fixed: nothing on this card reads today's date.
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

const research: ObligationDetail = {
  id: 'ob-1',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false },
  instrument: {
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
      instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
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
};

const ME = {
  user: { id: 'u1', name: 'Sara', locale: 'en' },
  tenant: { timezone: 'Europe/Stockholm' },
  permissions: ['library.read', 'problems.report'],
  enrolmentPending: false,
};

function renderIn(node: ReactNode, permissions: string[] = ['library.read', 'problems.report']) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
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
  segments: [
    { op: 'equal', text: 'Research from third parties may be received only if…' },
    { op: 'insert', text: 'The institution sets criteria for an annual assessment.' },
  ],
};

/** The server: /me for the format context and the permissions, then the card, the diff and the report. */
function serve(answer: ObligationDetail | number) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: ME };
    if (sent.path.endsWith('/diff')) return { status: 200, data: versionDiff };
    if (sent.path.endsWith('/problem-reports')) return { status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } };
    if (typeof answer === 'number') return { status: answer, data: { detail: 'no', code: answer === 404 ? 'not_found' : 'server_error' } };
    // "As of" a date before version 2 is the same record read again; the
    // version in force is what the server decides, so the test answers what
    // the date asked for.
    const asOf = (sent.params as { asOf?: string } | null)?.asOf;
    if (asOf === '2026-10-01') return { status: 200, data: { ...answer, version: answer.versions[1] } };
    return { status: 200, data: answer };
  });
}

describe('the language chips', () => {
  it('labels the original as the original and offers the reader a language the version does not hold', () => {
    expect(languageChoices([sv, en], 'en', 'en', t)).toEqual([
      { language: 'sv', label: 'Swedish, original', selected: false, hasText: true },
      { language: 'en', label: 'English', selected: true, hasText: true },
    ]);
    // A Swedish reader of a record with no Swedish text still gets a chip, and
    // it holds none. The names are in the reader's own language, not the text's.
    expect(languageChoices([en], 'en', 'sv', createT('sv'))).toEqual([
      { language: 'en', label: 'engelska', selected: true, hasText: true },
      { language: 'sv', label: 'svenska', selected: false, hasText: false },
    ]);
    expect(languageChoices([], 'en', 'en', t)).toEqual([{ language: 'en', label: 'English', selected: true, hasText: false }]);
  });

  it('finds the text of a language, and the original to go back to', () => {
    expect(textIn([sv, en], 'sv')).toEqual(sv);
    expect(textIn([sv, en], 'fi')).toBeNull();
    expect(originalLanguage([en, sv])).toBe('sv');
    // No row says it is the original: the first one stands in for it.
    expect(originalLanguage([en])).toBe('en');
    expect(originalLanguage([])).toBeNull();
  });
});

describe('ObligationScreen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('shows the header slots in order, the duty, its scope and where it comes from', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });

    // Instrument, regime, binding level: brand, information, information (INV-S3).
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['FFFS 2017:2', 'brand'],
      ['Securities', 'information'],
      ['Binding', 'information'],
    ]);

    // Scope: a brand pill per term, and plain words where the record restricts nothing.
    const scope = document.querySelector('[data-scope-panel]') as HTMLElement;
    expect(within(scope).getByText('Advice')).toHaveAttribute('data-pill', 'brand');
    expect(within(scope).getByText('Not client-specific')).toBeInTheDocument();
    expect(within(scope).getByText('Third-party research')).toBeInTheDocument();
    expect(within(scope).getByText('Research')).toHaveAttribute('data-pill', 'brand');

    const duty = document.querySelector('[data-duty-panel]') as HTMLElement;
    expect(within(duty).getByText('Governance')).toBeInTheDocument();
    expect(within(duty).getByText('5 years')).toBeInTheDocument();

    // Provenance: the source link, the verified date with no name, the draft's origin.
    const source = screen.getByRole('link', { name: 'FFFS 2017:2, 9 kap. 6 §' });
    expect(source).toHaveAttribute('href', 'https://www.fi.se/');
    expect(source).toHaveAttribute('rel', 'noopener noreferrer');
    expect(document.querySelector('[data-last-verified]')?.textContent).toBe('30 Jun 2026');
    expect(screen.getByText(/agent pipeline 0\.3, through proposal review/)).toBeInTheDocument();

    // Versions and the duties filed beside it.
    expect(document.querySelectorAll('[data-version-row]')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Disclose all costs and charges' })).toHaveAttribute('href', '/inventory/obligations/ob-2');

    // Nothing on the card claims the duty applies here, or that the bank complies.
    expect(document.querySelectorAll('[data-pending-panel]')).toHaveLength(2);
  });

  it('labels the machine translation and puts the original back behind a chip', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });

    expect(screen.getByText('Machine translation from Swedish. The original is authoritative.')).toBeInTheDocument();
    expect(document.querySelectorAll('[data-language-chips] button')).toHaveLength(2);
    expect(document.querySelector('[data-legal-text] [lang="en"]')?.textContent).toBe(en.text);

    fireEvent.click(screen.getByRole('button', { name: 'Swedish, original' }));
    await waitFor(() => expect(document.querySelector('[data-legal-text] [lang="sv"]')?.textContent).toBe(sv.text));
    // The original carries no label of its own.
    expect(screen.queryByText(/Machine translation from/)).not.toBeInTheDocument();
  });

  it('says so when the version holds no text in the reader\'s language, and offers the original', async () => {
    serve({ ...research, summary: sv, translations: [sv] });
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });

    fireEvent.click(screen.getByRole('button', { name: 'English' }));
    expect(await screen.findByText('No English text yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: 'Show the original' }));
    await waitFor(() => expect(document.querySelector('[data-legal-text] [lang="sv"]')?.textContent).toBe(sv.text));
  });

  it('reads a record with no title, no regime, no lineage and nobody named as verifier', async () => {
    serve({
      ...research,
      title: null,
      regime: null,
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
    expect(screen.queryByText('Securities')).not.toBeInTheDocument();
    expect(screen.getByText('Not verified yet')).toBeInTheDocument();
    expect(screen.getByText('The library files no other duty beside this one.')).toBeInTheDocument();
    expect(screen.getByText(/^12 Mar 2026.*through proposal review$/)).toBeInTheDocument();
  });

  describe('a version independent agents confirmed', () => {
    const sara = { id: 'u-9', name: 'Sara Lindqvist' };
    const confirmedByAgents = { verifiedOrigin: 'agent', confirmedByAgent: byAgents.confirmedByAgent, proposedByAgent: byAgents.proposedByAgent };

    async function open(record: ObligationDetail) {
      serve(record);
      renderIn(<ObligationScreen obligationId="ob-1" />);
      await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });
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
    tokenStore.set('tok');
    serve(500);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    expect(await screen.findByText('Could not load this obligation')).toBeInTheDocument();
  });

  it('shows the loading state while the card is on its way', () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    expect(document.querySelector('[data-loading-state]')).toBeInTheDocument();
  });

  it('reads the record as of a typed date and offers the way back to today', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });
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
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });
    fireEvent.change(screen.getByLabelText('As of'), { target: { value: '2017-01-01' } });
    expect(await screen.findByText('No version of this obligation was in force on 1 Jan 2017.')).toBeInTheDocument();
  });

  it('marks the sentences a version added and names both effective dates', async () => {
    serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });

    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    await waitFor(() => expect(document.querySelector('[data-diff-banner]')).toBeInTheDocument());
    expect(document.querySelector('[data-diff-banner]')).toHaveTextContent(
      'Comparing version 1 (in force since it began) with version 2 (in force from 1 Oct 2026).',
    );
    expect(document.querySelector('[data-diff-banner] [data-machine-confirmed]')).toBeNull();
    expect(document.querySelector('[data-legal-text] ins')?.textContent).toContain('The institution sets criteria for an annual assessment.');
    // Either side machine translated labels the whole comparison (INV-05).
    expect(screen.getByText('Machine translation from Swedish. The original is authoritative.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    await waitFor(() => expect(document.querySelector('[data-diff-banner]')).toBeNull());
  });

  it('offers "This looks wrong" only to a reader who may report, and acknowledges the report', async () => {
    serve(research);
    const withoutReport = renderIn(<ObligationScreen obligationId="ob-1" />, ['library.read']);
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });
    expect(screen.queryByRole('button', { name: 'This looks wrong' })).not.toBeInTheDocument();
    withoutReport.unmount();

    resetApiForTests();
    tokenStore.set('tok');
    const sent = serve(research);
    renderIn(<ObligationScreen obligationId="ob-1" />);
    await screen.findByRole('heading', { level: 1, name: 'Pay for third-party research only under the permitted models' });
    fireEvent.click(screen.getByRole('button', { name: 'This looks wrong' }));
    fireEvent.change(await screen.findByLabelText('What you see'), { target: { value: 'The English says annually.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }));
    expect(await screen.findByText('Report sent. Thank you.')).toBeInTheDocument();
    // What was on screen rides along: the version and the language being read.
    expect(sent.filter((call) => call.path.endsWith('/problem-reports')).map((call) => call.body)).toEqual([
      { description: 'The English says annually.', language: 'en', versionNumber: 1 },
    ]);
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
