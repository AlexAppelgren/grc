import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { defaultVersion, ProvisionTree } from './ProvisionTree';
import type { ProvisionNode } from '@/features/library/types';

// The provision tree on the instrument card (design/screens/tenant-instrument.html;
// INV-02, INV-04, INV-05): a disclosure list, versions chosen by chip and
// never by today's date, the transitional note, links to citing obligations,
// and "Show what changed" through the sentence-level diff.

const section: ProvisionNode = {
  id: 'pr-6',
  stableKey: 'fffs-2017-2/9-6',
  kind: { key: 'section', kind: 'unit', label: 'Section' },
  refLabel: '6 §',
  heading: 'Betalning för analys',
  path: 'FFFS 2017:2 > 9 kap. > 6 §',
  children: [],
  versions: [
    {
      versionNumber: 1,
      effectiveFrom: { date: '2018-01-03', precision: 'day' },
      effectiveTo: { date: '2026-09-30', precision: 'day' },
      transitionalNote: '',
      text: { text: 'Research payment under the earlier rules.', language: 'en', isOriginal: false, isMachine: true },
    },
    {
      versionNumber: 2,
      effectiveFrom: { date: '2026-10-01', precision: 'day' },
      effectiveTo: null,
      transitionalNote: 'The annual assessment is first due for research received after 1 October 2026.',
      text: { text: 'Research payment under the new rules.', language: 'en', isOriginal: false, isMachine: true },
    },
  ],
  inForceVersion: 1,
  obligations: [{ id: 'ob-1', title: { text: 'Pay for third-party research only under the permitted models', language: 'en', isOriginal: true, isMachine: false }, refLabel: 'Third-party payments' }],
};

const chapter: ProvisionNode = {
  id: 'pr-9',
  stableKey: 'fffs-2017-2/9',
  kind: { key: 'chapter', kind: 'division', label: 'Chapter' },
  refLabel: '9 kap.',
  heading: 'Skydd för investerare',
  path: 'FFFS 2017:2 > 9 kap.',
  children: [section],
  versions: [],
  inForceVersion: null,
  obligations: [],
};

function renderIn(node: ReactNode) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(<Wrapper>{<LocaleProvider locale="en">{node}</LocaleProvider>}</Wrapper>);
}

const diff = {
  fromVersion: 1,
  toVersion: 2,
  fromEffective: { date: '2018-01-03', precision: 'day' },
  toEffective: { date: '2026-10-01', precision: 'day' },
  language: 'en',
  isMachine: true,
  segments: [
    { op: 'delete', text: 'Research payment under the earlier rules.' },
    { op: 'insert', text: 'Research payment under the new rules.' },
  ],
};

function serve(nodes: ProvisionNode[], answer: typeof diff = diff) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
    if (sent.path.endsWith('/diff')) return { status: 200, data: answer };
    return { status: 200, data: nodes };
  });
}

describe('defaultVersion', () => {
  it('opens on the version in force, or the first one when none is', () => {
    expect(defaultVersion(section)).toBe(1);
    expect(defaultVersion({ ...section, inForceVersion: null })).toBe(1);
    expect(defaultVersion({ ...section, inForceVersion: null, versions: [] })).toBeNull();
  });
});

describe('ProvisionTree', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('renders the tree three levels deep, and defaults to the in-force version with its text', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" />);
    await screen.findByText('9 kap.');
    expect(screen.getByText('Skydd för investerare')).toBeVisible();
    expect(screen.getAllByText('6 §').length).toBeGreaterThan(0);
    expect(screen.getByText('Betalning för analys')).toBeVisible();
    // Version 1 is in force by default; its own text shows, machine-labelled.
    expect(screen.getByText('Research payment under the earlier rules.')).toBeVisible();
    expect(screen.getByText('Machine translation. The original is authoritative.')).toBeVisible();
    expect(screen.queryByText('Research payment under the new rules.')).toBeNull();
  });

  it('chooses a version by its own chip, never by relying on today, and shows its transitional note', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(screen.getByRole('button', { name: 'In force from 1 Oct 2026' }));
    expect(screen.getByText('Research payment under the new rules.')).toBeVisible();
    expect(screen.getByText('The annual assessment is first due for research received after 1 October 2026.')).toBeVisible();
    expect(screen.queryByText('Research payment under the earlier rules.')).toBeNull();
  });

  it('links to the obligations that cite the provision', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" />);
    const link = await screen.findByRole('link', { name: 'Pay for third-party research only under the permitted models' });
    expect(link).toHaveAttribute('href', '/inventory/obligations/ob-1');
  });

  it('opens the diff through "Show what changed", naming the two versions it compares and labelling a machine translation', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    await waitFor(() => expect(screen.getByText(/Research payment under the new rules\./)).toBeVisible());
    const text = document.querySelector('[data-legal-text]') as HTMLElement;
    expect(within(text).getByText('Research payment under the earlier rules.').tagName).toBe('DEL');
    expect(within(text).getByText('Research payment under the new rules.').tagName).toBe('INS');
    expect(document.querySelector('[data-diff-banner]')).toHaveTextContent(
      'Comparing version 1 (in force from 3 Jan 2018) with version 2 (in force from 1 Oct 2026).',
    );
    // Either side machine translated: the diff says so exactly as the text it replaces did.
    const labels = document.querySelectorAll('[data-machine-translation]');
    expect([...labels].map((label) => label.textContent)).toEqual(['Machine translation. The original is authoritative.']);
  });

  it('leaves the machine translation label off a diff between two texts a person wrote', async () => {
    serve([chapter], { ...diff, isMachine: false, language: 'sv' });
    renderIn(<ProvisionTree instrumentId="in-1" />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    await waitFor(() => expect(document.querySelector('[data-diff-banner]')).not.toBeNull());
    expect(document.querySelector('[data-machine-translation]')).toBeNull();
    expect(document.querySelector('[data-legal-text] [lang]')).toHaveAttribute('lang', 'sv');
  });

  it('leaves the diff chip and the version chips out of a unit with no text of its own', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" />);
    await screen.findByText('9 kap.');
    expect(screen.queryAllByRole('button', { name: 'Show what changed' })).toHaveLength(1);
  });

  it('shows the empty state for an instrument with no provisions yet', async () => {
    serve([]);
    renderIn(<ProvisionTree instrumentId="in-1" />);
    expect(await screen.findByText('No provisions yet')).toBeVisible();
  });
});
