import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { InstrumentScreen } from './InstrumentScreen';
import type { InstrumentDetail, Obligation } from '@/features/library/types';

// The instrument card (design/screens/tenant-instrument.html; INV-01, INV-06,
// FP-03): the header pills, the Identity panel, the source link, lineage
// grouped by relation, the obligations from this instrument, and every state
// the card names. Nothing here writes but "This looks wrong".

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
  lineage: [
    {
      relation: { key: 'amends', kind: null, label: 'Amends' },
      direction: 'incoming',
      instrument: { key: 'fffs-2026-11', shortName: 'FFFS 2026:11' },
      note: 'Amends FFFS 2017:2, in force 1 October 2026.',
      toRef: '',
    },
    {
      relation: { key: 'implements', kind: null, label: 'Implements' },
      direction: 'outgoing',
      instrument: { key: 'celex-32017l0593', shortName: 'Delegated directive (EU) 2017/593' },
      note: '',
      toRef: '',
    },
  ],
};

const researchObligation: Obligation = {
  id: 'ob-1',
  stableKey: 'obl-research-payments',
  refLabel: 'Third-party payments',
  title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false },
  instrument: { key: 'fffs-2017-2', shortName: 'FFFS 2017:2' },
  bindingLevel: { key: 'authority_regulation', kind: null, label: 'Supervisory regulation' },
  binding: true,
  dutyType: { key: 'governance', kind: null, label: 'Governance' },
  tags: [],
  scope: [],
  version: { versionNumber: 1, effectiveFrom: null },
  upcomingVersion: null,
  inFootprint: true,
  outsideReason: [],
  lastVerifiedAt: null,
  openChangeCount: 0,
  pendingApplicability: null,
  complianceStatus: null,
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

/** The server: /me, the card, its obligations and the report. */
function serve(answer: InstrumentDetail | number, obligations: Obligation[] = [researchObligation]) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: ME };
    if (sent.path === '/api/v1/obligations') return { status: 200, data: { items: obligations, total: obligations.length } };
    if (sent.path.endsWith('/provisions')) return { status: 200, data: [] };
    if (sent.path.endsWith('/problem-reports')) return { status: 201, data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } };
    if (typeof answer === 'number') return { status: answer, data: { detail: 'no', code: answer === 404 ? 'not_found' : 'server_error' } };
    return { status: 200, data: answer };
  });
}

describe('InstrumentScreen', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('shows the header pills, the identity panel, the source link and the obligations from this instrument', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1, name: 'FFFS 2017:2 om värdepappersrörelse' });

    // Short name and jurisdiction are brand, level and binding are information (INV-S1).
    const header = document.querySelectorAll('[data-header-pills] [data-pill]');
    expect([...header].map((pill) => [pill.textContent, pill.getAttribute('data-pill')])).toEqual([
      ['FFFS 2017:2', 'brand'],
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

    // An instrument with no provision tree yet shows the empty state, not an error.
    expect(await screen.findByText('No provisions yet')).toBeVisible();

    expect(await screen.findByText('Pay for third-party research only under the permitted models')).toBeInTheDocument();
  });

  it('groups the lineage by relation, and shows an empty state when there is none', async () => {
    serve(fffs);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    expect(within(document.querySelector('[data-lineage-group="Amended by"]') as HTMLElement).getByText('FFFS 2026:11')).toBeInTheDocument();
    expect(within(document.querySelector('[data-lineage-group="Amended by"]') as HTMLElement).getByText('Amends FFFS 2017:2, in force 1 October 2026.')).toBeInTheDocument();
    expect(within(document.querySelector('[data-lineage-group="Implements"]') as HTMLElement).getByText('Delegated directive (EU) 2017/593')).toBeInTheDocument();
    expect(document.querySelector('[data-lineage-group="Elaborated by"]')).toBeNull();

    serve({ ...fffs, lineage: [] });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('The library files no other instrument beside this one.')).toBeVisible();
  });

  it('shows the ELI when the instrument carries one, and "by <name>" when someone verified it', async () => {
    serve({ ...fffs, eliUri: 'http://data.europa.eu/eli/reg/2017/565', verifiedBy: { id: 'u-2', name: 'Johan Ek' } });
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('http://data.europa.eu/eli/reg/2017/565')).toBeInTheDocument();
    expect(document.querySelector('[data-last-verified]')?.textContent).toBe('30 Jun 2026 by Johan Ek');
  });

  it('shows the empty state when the instrument has no obligation yet', async () => {
    serve(fffs, []);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByText('This instrument has no obligation yet.')).toBeVisible();
  });

  it('offers a retry when the read fails, and Not found on a 404', async () => {
    const sent = serve(500);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(sent.filter((s) => s.path === '/api/v1/instruments/in-1').length).toBeGreaterThan(1));
    expect(screen.getByText('Could not load this instrument')).toBeVisible();

    serve(404);
    renderIn(<InstrumentScreen instrumentId="in-1" />);
    expect(await screen.findByRole('heading', { name: 'Not found' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Inventory' })).toHaveAttribute('href', '/inventory');
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
});
