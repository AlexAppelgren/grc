import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

const setTheme = vi.fn();
vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'light', setTheme }) }));

async function renderPage(contact = '') {
  vi.resetModules();
  vi.doMock('@/shared/brand', async (importOriginal) => ({ ...(await importOriginal<object>()), supportContact: contact }));
  const { PublicPage } = await import('./PublicPage');
  return render(
    <LocaleProvider locale="en">
      <PublicPage />
    </LocaleProvider>,
  );
}

// The demo picks its form from the width; jsdom has no media queries of its own.
function stubWidth(wide: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: wide, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
}

beforeEach(() => stubWidth(false));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.doUnmock('@/shared/brand');
  setTheme.mockReset();
});

describe('PublicPage', () => {
  it('leads with the plate headline and sends every Sign in to the passkey sign-in flow', async () => {
    await renderPage();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('A register of record for everything regulation asks of your bank.');
    const signIns = screen.getAllByRole('link', { name: 'Sign in' });
    expect(signIns.length).toBeGreaterThanOrEqual(3);
    for (const link of signIns) expect(link).toHaveAttribute('href', '/sign-in');
    for (const link of screen.getAllByRole('link', { name: 'Request access' })) expect(link).toHaveAttribute('href', '#request');
  });

  it('gives the first screen one thing to read: the headline, with no actions competing beside it', async () => {
    await renderPage();
    const hero = screen.getByRole('region', { name: 'A register of record for everything regulation asks of your bank.' });
    expect(within(hero).queryAllByRole('link')).toHaveLength(0);
    expect(within(hero).queryAllByRole('button')).toHaveLength(0);
    expect(within(hero).queryByRole('article')).toBeNull();
  });

  it('shows the demo right under the headline, and on a phone loads nothing until it is opened', async () => {
    const { container } = await renderPage();
    const demo = screen.getByRole('region', { name: 'Demo' });
    expect(container.querySelector('iframe')).toBeNull();
    fireEvent.click(within(demo).getByRole('button', { name: 'Open the demo' }));
    const dialog = await screen.findByRole('dialog', { name: 'Demo' });
    const frame = dialog.querySelector('iframe');
    expect(frame).toHaveAttribute('name', 'bleqq-demo');
    expect(frame).toHaveAttribute('src', '/');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close the demo' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('frames the app in the page on a wide screen, loading as it scrolls near', async () => {
    stubWidth(true);
    await renderPage();
    const frame = await screen.findByTitle("Compliance Watch with a sample bank's data");
    expect(frame).toHaveAttribute('name', 'bleqq-demo');
    expect(frame).toHaveAttribute('loading', 'lazy');
  });

  it('keeps Sign in as the primary of the two actions in the top bar, on the right', async () => {
    await renderPage();
    const bar = screen.getByRole('banner');
    const actions = within(bar).getAllByRole('link').filter((link) => link.textContent !== '');
    const names = actions.map((link) => link.textContent);
    expect(names.slice(-2)).toEqual(['Request access', 'Sign in']);
    // The app's neutral primary, not the brand green: the bar sits on the page's own paper.
    expect(actions.at(-1)).toHaveClass('bg-button');
    expect(bar).toHaveClass('bg-page');
  });

  it('points every section link at a section that is on the page', async () => {
    const { container } = await renderPage();
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual(['Method', 'Zones', 'Coverage', 'Assurance', 'Questions']);
    for (const link of links) {
      const id = link.getAttribute('href')?.slice(1) ?? '';
      expect(container.querySelector(`section#${id}`), id).not.toBeNull();
    }
    expect(container.querySelector('section#request')).not.toBeNull();
  });

  it('numbers the sections with a marginal section reference', async () => {
    await renderPage();
    for (const number of [1, 2, 3, 4, 5, 6, 7]) expect(screen.getByText(`§ ${number}`)).toBeInTheDocument();
  });

  it('offers no mail link while no contact address is configured', async () => {
    await renderPage();
    expect(screen.queryByRole('link', { name: 'Write to us' })).toBeNull();
    expect(screen.queryByText(/write to us and we will arrange an introduction/)).toBeNull();
    expect(screen.getByText('If your bank already uses bleqq, your administrator sends the invitation.')).toBeInTheDocument();
  });

  it('opens a mail to the configured contact with the subject filled in', async () => {
    await renderPage('hello@example.com');
    expect(screen.getByRole('link', { name: 'Write to us' })).toHaveAttribute('href', 'mailto:hello@example.com?subject=Request%20access%20to%20bleqq');
    expect(screen.getByText(/write to us and we will arrange an introduction/)).toBeInTheDocument();
  });

  it('switches to the dark theme from the footer', async () => {
    await renderPage();
    const footer = screen.getByRole('contentinfo');
    // jsdom applies no Tailwind, so both labels are in the name here; the real
    // page hides one by the theme class (public.journey.spec.ts checks that).
    fireEvent.click(within(footer).getByRole('button', { name: /Dark theme/ }));
    expect(setTheme).toHaveBeenCalledWith('dark');
  });
});
