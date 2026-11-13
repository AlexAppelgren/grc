import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CLAMP_LINES } from '@/features/library/rule-words-presentation';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { defaultVersion, ProvisionTree } from './ProvisionTree';
import type { ProvisionNode } from '@/features/library/types';

// The provision tree on the instrument card (design/screens/tenant-instrument.html;
// INV-02, INV-04, INV-05, D-142): a disclosure list, versions chosen by chip and
// never by today's date, each version's text as the rule's own words (the
// reader's language first, a chip per language, the line that is always true of
// it), the transitional note, links to citing obligations, and "Show what
// changed" through the sentence-level diff in the language shown.

type VersionRow = ProvisionNode['versions'][number];

const earlier: VersionRow = {
  versionNumber: 1,
  effectiveFrom: { date: '2018-01-03', precision: 'day' },
  effectiveTo: { date: '2026-09-30', precision: 'day' },
  transitionalNote: '',
  text: { text: 'Research payment under the earlier rules.', language: 'en', isOriginal: false, isMachine: true },
  texts: [
    { text: 'Betalning för analys enligt de äldre reglerna.', language: 'sv', isOriginal: true, isMachine: false },
    { text: 'Research payment under the earlier rules.', language: 'en', isOriginal: false, isMachine: true },
  ],
};

const amended: VersionRow = {
  versionNumber: 2,
  effectiveFrom: { date: '2026-10-01', precision: 'day' },
  effectiveTo: null,
  transitionalNote: 'The annual assessment is first due for research received after 1 October 2026.',
  text: { text: 'Research payment under the new rules.', language: 'en', isOriginal: false, isMachine: true },
  texts: [
    { text: 'Betalning för analys enligt de nya reglerna.', language: 'sv', isOriginal: true, isMachine: false },
    { text: 'Research payment under the new rules.', language: 'en', isOriginal: false, isMachine: true },
  ],
};

const section: ProvisionNode = {
  id: 'pr-6',
  stableKey: 'fffs-2017-2/9-6',
  kind: { key: 'section', kind: 'unit', label: 'Section' },
  refLabel: '6 §',
  heading: 'Betalning för analys',
  path: 'FFFS 2017:2 > 9 kap. > 6 §',
  children: [],
  versions: [earlier, amended],
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

function renderIn(node: ReactNode, locale: 'en' | 'sv' = 'en') {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(<Wrapper>{<LocaleProvider locale={locale}>{node}</LocaleProvider>}</Wrapper>);
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

const SOURCE = 'https://www.iso.org/standard/27001';

function serve(nodes: ProvisionNode[], answer: typeof diff = diff) {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { id: 'u1', name: 'Sara', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions: [], enrolmentPending: false } };
    if (sent.path.endsWith('/diff')) return { status: 200, data: answer };
    return { status: 200, data: nodes };
  });
}

/** A unit's own block; its first label and text are its own, before any child's. */
const unit = (key = 'fffs-2017-2/9-6') => document.querySelector(`[data-provision="${key}"]`) as HTMLElement;
const label = (key?: string) => unit(key).querySelector('[data-provision-label]')?.textContent;
const shownText = (key?: string) => unit(key).querySelector('[data-provision-text]') as HTMLElement;
const languageChips = (key?: string) => within(unit(key).querySelector('[data-provision-languages]') as HTMLElement);
const diffReads = (sent: { path: string; params?: unknown }[]) => sent.filter((request) => request.path.endsWith('/diff')).map((request) => request.params);

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
  afterEach(() => vi.restoreAllMocks());

  it('renders the tree three levels deep, and opens the in-force version in English for an English reader, labelled', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('9 kap.');
    expect(screen.getByText('Skydd för investerare')).toBeVisible();
    expect(screen.getAllByText('6 §').length).toBeGreaterThan(0);
    expect(screen.getByText('Betalning för analys')).toBeVisible();
    // Version 1 is in force by default; its English machine translation opens and says what it is.
    expect(shownText()).toHaveTextContent('Research payment under the earlier rules.');
    expect(shownText()).toHaveAttribute('lang', 'en');
    expect(label()).toBe('Machine translation from Swedish. The original is authoritative.');
    expect(languageChips().getAllByRole('button').map((chip) => [chip.textContent, chip.getAttribute('aria-pressed')])).toEqual([
      ['Swedish, original', 'false'],
      ['English', 'true'],
    ]);
    expect(screen.queryByText('Research payment under the new rules.')).toBeNull();
  });

  it('opens the Swedish original for a Swedish reader, labelled in Swedish', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />, 'sv');
    await screen.findByText('Betalning för analys');
    expect(label()).toBe('svenska, original');
    expect(shownText()).toHaveTextContent('Betalning för analys enligt de äldre reglerna.');
    expect(shownText()).toHaveAttribute('lang', 'sv');
  });

  it('switches to the original by its chip, and keeps that language when another version is chosen', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(languageChips().getByRole('button', { name: 'Swedish, original' }));
    expect(label()).toBe('Swedish, original');
    expect(shownText()).toHaveTextContent('Betalning för analys enligt de äldre reglerna.');
    fireEvent.click(screen.getByRole('button', { name: 'In force from 1 Oct 2026' }));
    expect(label()).toBe('Swedish, original');
    expect(shownText()).toHaveTextContent('Betalning för analys enligt de nya reglerna.');
  });

  it("labels a Finnish act's Swedish text as the authority's own, never as a translation", async () => {
    const finnish: ProvisionNode = {
      ...section,
      id: 'pr-fi',
      stableKey: 'fi-laki-2014-610/1',
      versions: [
        {
          ...earlier,
          effectiveTo: null,
          text: null,
          texts: [
            { text: 'Luottolaitoksen on…', language: 'fi', isOriginal: true, isMachine: false },
            { text: 'Kreditinstitutet ska…', language: 'sv', isOriginal: false, isMachine: false },
            { text: 'The credit institution must…', language: 'en', isOriginal: false, isMachine: true },
          ],
        },
      ],
    };
    serve([finnish]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />, 'sv');
    await screen.findByText('Betalning för analys');
    expect(label(finnish.stableKey)).toBe('svenska, officiell språkversion');
    fireEvent.click(languageChips(finnish.stableKey).getByRole('button', { name: 'engelska' }));
    expect(label(finnish.stableKey)).toBe('Maskinöversättning från finska. Originalet gäller.');
    fireEvent.click(languageChips(finnish.stableKey).getByRole('button', { name: 'finska, original' }));
    expect(label(finnish.stableKey)).toBe('finska, original');
  });

  it('keeps the paragraph breaks of a text and clamps a long one, with "Show all"', async () => {
    // jsdom lays nothing out: the clamped box's heights are set as a browser would measure them.
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(900);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(540);
    const long = Array.from({ length: CLAMP_LINES + 2 }, (_, i) => `${i + 1}. Stycke.`).join('\n');
    serve([{ ...section, versions: [{ ...earlier, texts: [{ text: long, language: 'sv', isOriginal: true, isMachine: false }] }] }]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('Betalning för analys');
    expect(shownText().textContent).toBe(long);
    expect(shownText().className).toContain('whitespace-pre-wrap');
    expect(shownText().className).toContain('overflow-hidden');
    // One text needs no chips.
    expect(unit().querySelector('[data-provision-languages]')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(shownText().className).not.toContain('overflow-hidden');
  });

  it('says in one muted line when the version chosen holds no text', async () => {
    serve([{ ...section, versions: [earlier, { ...amended, text: null, texts: [] }] }]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(screen.getByRole('button', { name: 'In force from 1 Oct 2026' }));
    expect(unit().querySelector('[data-provision-not-held]')).toHaveTextContent("The library does not hold this rule's wording yet.");
    expect(unit().querySelector('[data-provision-text]')).toBeNull();
  });

  it('shows no comparison banner, and reads no diff, while the version chosen holds no text', async () => {
    const sent = serve([{ ...section, versions: [earlier, { ...amended, text: null, texts: [] }] }]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(screen.getByRole('button', { name: 'In force from 1 Oct 2026' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    expect(unit().querySelector('[data-provision-not-held]')).not.toBeNull();
    expect(document.querySelector('[data-diff-banner]')).toBeNull();
    expect(diffReads(sent)).toEqual([]);
    // Back on a version with text, the comparison opens.
    fireEvent.click(screen.getByRole('button', { name: 'In force 3 Jan 2018 to 30 Sept 2026' }));
    await waitFor(() => expect(document.querySelector('[data-diff-banner]')).not.toBeNull());
  });

  it('labels the diff by what the server answered, not by the text shown', async () => {
    // The English machine translation is shown, but the diff comes back in the Swedish original.
    serve([chapter], { ...diff, isMachine: false, language: 'sv' });
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('Betalning för analys');
    expect(label()).toBe('Machine translation from Swedish. The original is authoritative.');
    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    await waitFor(() => expect(label()).toBe('Swedish, original'));
    expect(shownText()).toHaveAttribute('lang', 'sv');
  });

  it('chooses a version by its own chip, never by relying on today, and shows its transitional note', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(screen.getByRole('button', { name: 'In force from 1 Oct 2026' }));
    expect(screen.getByText('Research payment under the new rules.')).toBeVisible();
    expect(screen.getByText('The annual assessment is first due for research received after 1 October 2026.')).toBeVisible();
    expect(screen.queryByText('Research payment under the earlier rules.')).toBeNull();
  });

  it('links to the obligations that cite the provision', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    const link = await screen.findByRole('link', { name: 'Pay for third-party research only under the permitted models' });
    expect(link).toHaveAttribute('href', '/inventory/obligations/ob-1');
  });

  it('opens the diff through "Show what changed" in the language shown, naming the two versions and labelling a machine translation', async () => {
    const sent = serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
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
    expect(label()).toBe('Machine translation from Swedish. The original is authoritative.');
    expect(diffReads(sent)).toEqual([{ lang: 'en' }]);
  });

  it('takes the diff again in the original once its chip is pressed, and labels it the original', async () => {
    const sent = serve([chapter], { ...diff, isMachine: false, language: 'sv' });
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('Betalning för analys');
    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    fireEvent.click(languageChips().getByRole('button', { name: 'Swedish, original' }));
    await waitFor(() => expect(diffReads(sent)).toContainEqual({ lang: 'sv' }));
    await waitFor(() => expect(label()).toBe('Swedish, original'));
    expect(shownText()).toHaveAttribute('lang', 'sv');
    expect(unit().querySelector('[data-transitional-note]')).toBeNull();
  });

  it('leaves the diff chip and the version chips out of a unit with no text of its own', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await screen.findByText('9 kap.');
    expect(screen.queryAllByRole('button', { name: 'Show what changed' })).toHaveLength(1);
  });

  it('renders nothing for an instrument with no provisions yet, once the read answers', async () => {
    const sent = serve([]);
    const { container } = renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await waitFor(() => expect(sent.some((request) => request.path.endsWith('/provisions'))).toBe(true));
    await waitFor(() => expect(container.querySelector('[data-provision-tree]')).toBeNull());
    expect(document.querySelector('[data-loading-state]')).toBeNull();
  });

  it("says a standard's text is licensed and links the catalogue, without reading a tree", async () => {
    const sent = serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind="standard" sourceUrl={SOURCE} />);
    const panel = document.querySelector('[data-provisions-licensed]') as HTMLElement;
    expect(within(panel).getByRole('heading', { name: 'The text is licensed' })).toBeVisible();
    expect(within(panel).getByText('The text of this standard is licensed and not held here.')).toBeVisible();
    const link = within(panel).getByRole('link', { name: "See it in the publisher's catalogue" });
    expect(link).toHaveAttribute('href', SOURCE);
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByText('9 kap.')).toBeNull();
    expect(sent.some((request) => request.path.endsWith('/provisions'))).toBe(false);
  });

  it('shows the loading state until the tree arrives', async () => {
    serve([chapter]);
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    expect(document.querySelector('[data-provision-tree] [aria-busy="true"]')).not.toBeNull();
    await screen.findByText('9 kap.');
  });

  it('offers a retry when the tree cannot be read', async () => {
    installAdapter(() => ({ status: 500, data: { detail: 'no', code: 'server_error' } }));
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    expect(await screen.findByText('Could not load the provisions')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeVisible();
  });

  it('names the missing grant instead of a retry when the tree is denied', async () => {
    installAdapter(() => ({ status: 403, data: { detail: 'You do not have access to this.', code: 'permission_denied' } }));
    renderIn(<ProvisionTree instrumentId="in-1" levelKind={null} sourceUrl={SOURCE} />);
    await waitFor(() => expect(document.querySelector('[data-provisions-denied] [role="alert"]')).toHaveTextContent('You do not have access to this.'));
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
  });
});
