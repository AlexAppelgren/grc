import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { framesOf, sseResponse, stubFetch } from '@/features/search/ask-testing';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import { AskScreen } from './AskScreen';

// /ask (design/screens/tenant-ask.html): the "as of" date rides in the URL,
// the question never does, and "Search the inventory" opens the inventory.

const nav = { search: '', replace: vi.fn(), push: vi.fn() };

vi.mock('next/navigation', () => ({
  usePathname: () => '/ask',
  useRouter: () => ({ replace: nav.replace, push: nav.push }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

function renderScreen(): void {
  const { wrapper: Query } = queryWrapper();
  const Wrapper = Query as (props: { children: ReactNode }) => ReactNode;
  render(
    <Wrapper>
      <LocaleProvider locale="en">
        <AskScreen />
      </LocaleProvider>
    </Wrapper>,
  );
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
  nav.search = '';
  nav.replace.mockReset();
  nav.push.mockReset();
  // A browser resolves the relative route against the page; Node needs an origin.
  api.defaults.baseURL = 'http://app.test';
  installAdapter(() => ({ status: 200, data: { user: { locale: 'en' }, tenant: null } }));
});

afterEach(() => {
  api.defaults.baseURL = '';
  vi.unstubAllGlobals();
});

describe('AskScreen', () => {
  it('asks with the "as of" date from the URL, and the question never reaches the URL', async () => {
    nav.search = 'asOf=2026-06-01';
    const requests = stubFetch(() => sseResponse(framesOf([{ event: 'start', id: 'ans-1' }])));
    renderScreen();
    expect(screen.getByRole('heading', { level: 1, name: 'Ask' })).toBeVisible();
    expect(screen.getByText('Showing the versions in force on 1 Jun 2026.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to today' })).toHaveAttribute('href', '/ask');

    fireEvent.change(screen.getByRole('searchbox', { name: 'Question' }), { target: { value: 'What about research payments?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(await requests[0]?.json()).toEqual({ question: 'What about research payments?', asOf: '2026-06-01' });
    for (const [href] of nav.replace.mock.calls) expect(String(href)).not.toContain('research');
  });

  it('keeps the "as of" date in the URL as a plain date', () => {
    renderScreen();
    fireEvent.change(screen.getByLabelText('As of'), { target: { value: '2026-06-30' } });
    expect(nav.replace).toHaveBeenCalledWith('/ask?asOf=2026-06-30');
  });

  it('"Search the inventory" opens the inventory and leaves the question behind', async () => {
    stubFetch(() =>
      sseResponse(
        framesOf([
          { event: 'start', id: 'ans-1' },
          { event: 'answer', answer: { id: 'ans-1', question: 'q', asOf: '2026-06-01', statements: [], citations: [], noAnswer: true, model: '', aiGenerated: true, createdAt: '2026-06-01T09:00:00Z' }, stopReason: null },
        ]),
      ),
    );
    renderScreen();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Question' }), { target: { value: 'crypto custody' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Search the inventory' }));
    expect(nav.push).toHaveBeenCalledWith('/inventory');
  });
});
