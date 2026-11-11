import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

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

// The demo picks its form from the width and the ink its mode from reduced motion;
// jsdom has no media queries of its own.
function stubMedia({ wide = false, reduce = false } = {}) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('min-width') ? wide : query.includes('reduced-motion') ? reduce : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

// A stand-in WebGL context: every constant is 1 and every call answers with an
// object, so shaders compile and programs link. Only the framebuffer check is
// real, which decides whether the simulation's half-float targets exist. No
// pixel is ever read.
function stubWebGl(context: 'none' | 'webgl2' | 'webgl', framebuffers = true) {
  const gl = new Proxy(
    {},
    {
      get: (_target, key) => {
        if (typeof key !== 'string') return undefined;
        if (/^[A-Z0-9_]+$/.test(key)) return 1;
        if (key === 'checkFramebufferStatus') return () => (framebuffers ? 1 : 0);
        return () => ({});
      },
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(((id: string) => (id === context ? gl : null)) as never);
}

function ink(container: HTMLElement) {
  return container.querySelector('[data-ink]');
}

const ENTRIES = ['bleqq', 'demo', 'spreadsheet', 'inbox', 'watch', 'inventory', 'ask', 'evidence', 'library', 'zone', 'signoff', 'source', 'assurance', 'question', 'request'];

beforeEach(() => {
  stubMedia();
  stubWebGl('none');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.doUnmock('@/shared/brand');
});

describe('PublicPage', () => {
  it('opens on the deck and its two actions, with the h1 for screen readers and the origin of the name beside the deck', async () => {
    const { container } = await renderPage();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    const entry = container.querySelector('section#bleqq') as HTMLElement;
    // The ink logo above shows the name, so the h1 is not drawn a second time.
    expect(within(entry).getByRole('heading', { level: 1 })).toHaveTextContent('bleqq');
    expect(within(entry).getByRole('heading', { level: 1 })).toHaveClass('sr-only');
    expect(within(entry).queryByText('[blɛkː]')).toBeNull();
    // On a wide screen the origin sits on the right of the deck.
    expect(within(entry).getByText('noun, from the Swedish word bläck, ink')).toHaveClass('min-[860px]:order-2', 'min-[860px]:text-right');
    expect(within(entry).getByText("One inventory of your bank's obligations.")).toBeInTheDocument();
    expect(within(entry).getByRole('link', { name: 'Try out our demo' })).toHaveAttribute('href', '#demo');
    expect(within(entry).getByRole('link', { name: 'Request access' })).toHaveAttribute('href', '#request');
    // The main action is first in the source, and a phone moves it to the right.
    expect(within(entry).getByRole('link', { name: 'Try out our demo' })).toHaveClass('max-[700px]:order-2');
  });

  it('carries every entry in dictionary order, each named by its headword', async () => {
    const { container } = await renderPage();
    const sections = [...container.querySelectorAll('main section[id]')].map((section) => section.id);
    expect(sections).toEqual(ENTRIES);
    const names = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent);
    expect(names).toEqual([
      'demo',
      'spreadsheetsee inventory',
      'inboxsee watch',
      'watch',
      'inventory',
      'ask',
      'evidence',
      'library',
      'zone',
      'sign off',
      'source',
      'assurance',
      'question',
      'Access is by invitation.',
    ]);
  });

  it('strikes out the spreadsheet and the inbox and corrects each claim in pen', async () => {
    const { container } = await renderPage();
    const spreadsheet = container.querySelector('section#spreadsheet') as HTMLElement;
    const heading = within(spreadsheet).getByRole('heading', { level: 2 });
    expect(heading.querySelector('del')).toHaveTextContent('spreadsheet');
    expect(heading.querySelector('ins')).toHaveTextContent('see inventory');
    expect(within(spreadsheet).getByText('noun, obsolete')).toBeInTheDocument();
    const struck = [...spreadsheet.querySelectorAll('li del')].map((del) => del.textContent);
    const pen = [...spreadsheet.querySelectorAll('li ins')].map((ins) => ins.textContent);
    expect(struck).toEqual(['is gone', 'is one word in a cell']);
    expect(pen).toEqual(['stays readable, with the dates it applied.', 'carries a name, the evidence and a second signature.']);

    const inbox = container.querySelector('section#inbox') as HTMLElement;
    expect(inbox.querySelector('h2 ins')).toHaveTextContent('see watch');
    expect(inbox.querySelector('p del')).toHaveTextContent('whatever reached you');
  });

  it('shows the redline finished until the browser can watch the entries, then draws it when each comes into view', async () => {
    const { container } = await renderPage();
    // Without IntersectionObserver nothing waits, so the strike is simply there.
    expect(container.querySelector('section#spreadsheet')).not.toHaveAttribute('data-reveal');

    const seen: ((changes: { isIntersecting: boolean }[]) => void)[] = [];
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(callback: (changes: { isIntersecting: boolean }[]) => void) {
          seen.push(callback);
        }
        observe() {}
        disconnect() {}
      },
    );
    const again = await renderPage();
    const spreadsheet = again.container.querySelector('section#spreadsheet') as HTMLElement;
    const inbox = again.container.querySelector('section#inbox') as HTMLElement;
    expect(spreadsheet).toHaveAttribute('data-reveal', 'waiting');
    expect(inbox).toHaveAttribute('data-reveal', 'waiting');
    // One observer for the ink, one per struck entry, in page order after it.
    act(() => seen.at(-2)?.([{ isIntersecting: true }]));
    expect(spreadsheet).toHaveAttribute('data-reveal', 'seen');
    expect(inbox).toHaveAttribute('data-reveal', 'waiting');
  });

  it('points every cross-reference and section link at an entry on the page', async () => {
    const { container } = await renderPage();
    const refs = [...(container.querySelector('section#bleqq') as HTMLElement).querySelectorAll('p a')];
    expect(refs.map((link) => link.textContent)).toEqual(['watch', 'inventory', 'ask', 'evidence']);
    expect(refs[0]?.closest('p')).toHaveTextContent('See also watch, inventory, ask, evidence.');
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual(['Demo', 'Method', 'Sources']);
    for (const link of container.querySelectorAll('a[href^="#"]')) {
      const id = link.getAttribute('href')?.slice(1) ?? '';
      expect(container.querySelector(`#${id}`), id).not.toBeNull();
    }
  });

  it('makes Sign in the main action, filled and on the right, in the sticky bar and the closing section', async () => {
    const { container } = await renderPage('hello@example.com');
    const bar = screen.getByRole('banner');
    expect(bar).toHaveClass('sticky');
    const actions = within(bar).getAllByRole('link').slice(-2);
    expect(actions.map((link) => link.textContent)).toEqual(['Request access', 'Sign in']);
    expect(actions[0]).toHaveAttribute('href', '#request');
    expect(actions[0]).not.toHaveClass('bg-public-paper');
    expect(actions[1]).toHaveClass('bg-public-paper', 'max-[700px]:order-2');
    const closing = within(container.querySelector('section#request') as HTMLElement);
    expect(closing.getByRole('link', { name: 'Sign in' })).toHaveClass('bg-public-paper');
    expect(closing.getByRole('link', { name: 'Request access' })).not.toHaveClass('bg-public-paper');
    for (const link of screen.getAllByRole('link', { name: 'Sign in' })) expect(link).toHaveAttribute('href', '/sign-in');
  });

  it('lists the six steps of a sign-off and the five jurisdictions with their languages', async () => {
    const { container } = await renderPage();
    const signOff = container.querySelector('section#signoff') as HTMLElement;
    expect([...signOff.querySelectorAll('ol b')].map((name) => name.textContent)).toEqual(['Sighted', 'Proposed', 'Confirmed', 'Applied', 'Assessed', 'Signed off']);
    const source = within(container.querySelector('section#source') as HTMLElement).getByRole('table', { name: 'Nordic and EU sources, in the languages they are published in' });
    expect(within(source).getAllByRole('rowheader').map((cell) => cell.textContent)).toEqual(['Sweden', 'Denmark', 'Norway', 'Finland', 'European Union']);
    expect(within(source).getByText('Finnish, Swedish, English')).toBeInTheDocument();
  });

  it('shows a picture of the demo in the demo entry, and on a phone opens it full screen only when asked', async () => {
    const { container } = await renderPage();
    const demo = container.querySelector('section#demo') as HTMLElement;
    expect(within(demo).getAllByRole('img', { name: "The demo's Today screen, with what is coming for Example Bank AB" }).length).toBeGreaterThan(0);
    expect(container.querySelector('iframe')).toBeNull();
    fireEvent.click(within(demo).getByRole('button', { name: 'Try out our demo' }));
    const dialog = await screen.findByRole('dialog', { name: 'Demo' });
    const frame = dialog.querySelector('iframe');
    expect(frame).toHaveAttribute('name', 'bleqq-demo');
    expect(frame).toHaveAttribute('src', '/');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Start over' }));
    expect(dialog.querySelector('iframe')).not.toBe(frame);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('on a wide screen runs the live demo in place, and its skip link lands on the entry after it', async () => {
    stubMedia({ wide: true });
    const { container } = await renderPage();
    const frame = await screen.findByTitle("Compliance Watch with a sample bank's data");
    expect(frame).toHaveAttribute('name', 'bleqq-demo');
    expect(frame).not.toHaveFocus();
    expect(screen.getByRole('link', { name: 'Skip the demo' })).toHaveAttribute('href', '#case');
    expect(container.querySelector('#case section')).toHaveAttribute('id', 'spreadsheet');
  });

  it('has one appearance: the page is green and its demo pictures dark, whatever the theme', async () => {
    const { container } = await renderPage();
    const page = container.querySelector('[data-public-page]');
    expect(page).toHaveClass('dark', 'bg-brand');
    expect(screen.queryByRole('button', { name: /theme/i })).toBeNull();
  });

  it('offers no mail link while no contact address is configured, and says who sends the invitation', async () => {
    const { container } = await renderPage();
    const closing = container.querySelector('section#request') as HTMLElement;
    expect(within(closing).queryByRole('link', { name: 'Request access' })).toBeNull();
    expect(within(closing).getByText('If your bank already uses bleqq, your administrator sends the invitation.')).toBeInTheDocument();
    expect(within(closing).getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/sign-in');
  });

  it('opens a mail to the configured contact with the subject filled in from the closing Request access', async () => {
    const { container } = await renderPage('hello@example.com');
    const closing = container.querySelector('section#request') as HTMLElement;
    expect(within(closing).getByRole('link', { name: 'Request access' })).toHaveAttribute('href', 'mailto:hello@example.com?subject=Request%20access%20to%20bleqq');
    expect(within(closing).queryByText(/your administrator sends the invitation/)).toBeNull();
  });

  describe('the ink behind the logo', () => {
    it('keeps the CSS background, and hides the canvas, when the browser has no WebGL', async () => {
      const { container } = await renderPage();
      expect(ink(container)).toHaveAttribute('data-ink', 'css');
      expect(ink(container)).toHaveAttribute('aria-hidden', 'true');
      expect(container.querySelector('canvas')).toHaveAttribute('hidden');
    });

    it('runs the fluid simulation on WebGL2 half-float targets', async () => {
      stubWebGl('webgl2');
      const { container } = await renderPage();
      expect(ink(container)).toHaveAttribute('data-ink', 'fluid');
      expect(container.querySelector('canvas')).not.toHaveAttribute('hidden');
    });

    it('animates the resting pattern when the simulation cannot start', async () => {
      stubWebGl('webgl2', false);
      expect(ink((await renderPage()).container)).toHaveAttribute('data-ink', 'pattern');
      stubWebGl('webgl');
      expect(ink((await renderPage()).container)).toHaveAttribute('data-ink', 'pattern');
    });

    it('draws one still frame under prefers-reduced-motion', async () => {
      stubMedia({ reduce: true });
      stubWebGl('webgl2');
      expect(ink((await renderPage()).container)).toHaveAttribute('data-ink', 'still');
    });
  });
});
