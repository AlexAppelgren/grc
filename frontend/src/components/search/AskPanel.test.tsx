import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { framesOf, sseResponse, stubFetch } from '@/features/search/ask-testing';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import { AskPanel } from './AskPanel';

// Ask (design/screens/tenant-ask.html): every state the card names, the
// stream read statement by statement through the one axios instance, and
// the verdict a reader gives. The network under the fetch adapter answers
// as the server's event stream does; the JSON reads go through the test
// adapter.

const QUESTION = 'What are our obligations on research payments?';

const STATEMENT = { text: 'Research is paid from own resources or a research payment account.', citationIndexes: [1] };
const PENDING = {
  text: 'An annual assessment of the research is required.',
  citationIndexes: [2],
  pendingChangeId: 'chg-1',
  pendingChangeLabel: 'Research assessment',
  pendingChangeInForceOn: '2026-10-01',
  pendingChangeInForceOnPrecision: 'day' as const,
};
const CITATIONS = [
  { index: 2, obligationId: 'ob-2', versionNo: 2, instrumentShortName: 'FFFS 2017:2', refLabel: '9 kap. 6 §' },
  { index: 1, obligationId: 'ob-1', versionNo: 1, instrumentShortName: 'FFFS 2017:2', refLabel: '9 kap. 10 §' },
];

function answer(overrides: Record<string, unknown> = {}) {
  return {
    id: 'ans-1',
    question: QUESTION,
    asOf: '2026-06-01',
    statements: [STATEMENT, PENDING],
    citations: CITATIONS,
    noAnswer: false,
    model: 'mock',
    aiGenerated: true,
    createdAt: '2026-06-01T09:00:00Z',
    ...overrides,
  };
}

function answered(overrides: Record<string, unknown> = {}, stopReason: string | null = 'end_turn') {
  return framesOf([
    { event: 'start', id: 'ans-1' },
    { event: 'statement', statement: STATEMENT },
    { event: 'statement', statement: PENDING },
    { event: 'answer', answer: answer(overrides), stopReason },
  ]);
}

const onSearchInstead = vi.fn();

function serve(script: (sent: Sent) => Answer = () => ({ status: 204 })): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: { user: { locale: 'en' }, tenant: null } };
    return script(sent);
  });
}

function renderPanel({ asOf = '', lang = '' }: { asOf?: string; lang?: string } = {}): void {
  const { wrapper: Query } = queryWrapper();
  const shell = (children: ReactNode) => (
    <Query>
      <LocaleProvider locale="en">{children}</LocaleProvider>
    </Query>
  );
  render(shell(<AskPanel asOf={asOf} lang={lang} onSearchInstead={onSearchInstead} />));
}

function ask(question = QUESTION): void {
  fireEvent.change(screen.getByRole('searchbox', { name: 'Question' }), { target: { value: question } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
}

beforeEach(() => {
  resetApiForTests();
  // A browser resolves the relative route against the page; Node needs an origin.
  api.defaults.baseURL = 'http://app.test';
  tokenStore.set('tok');
  onSearchInstead.mockClear();
});

afterEach(() => {
  api.defaults.baseURL = '';
  vi.unstubAllGlobals();
});

describe('AskPanel', () => {
  it('starts empty and asks nothing until a question is sent', () => {
    serve();
    const requests = stubFetch(() => sseResponse(answered()));
    renderPanel();
    expect(screen.getByRole('heading', { name: 'Ask the inventory a question' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(requests).toHaveLength(0);
  });

  it('sends the question with the carried "as of" and language, and nothing else', async () => {
    serve();
    const requests = stubFetch(() => sseResponse(answered()));
    renderPanel({ asOf: '2026-06-01', lang: 'sv' });
    ask();
    await screen.findByText(STATEMENT.text);
    expect(await requests[0]?.json()).toEqual({ question: QUESTION, asOf: '2026-06-01', lang: 'sv' });
  });

  it('shows the loading state until the first statement arrives', async () => {
    serve();
    stubFetch(() => new Promise<Response>(() => undefined));
    renderPanel();
    ask();
    expect(await screen.findByRole('status', { busy: true })).toBeVisible();
  });

  it('shows each statement as it arrives, labelled AI output, before the answer closes', async () => {
    serve();
    let finish: () => void = () => undefined;
    const encoder = new TextEncoder();
    stubFetch(
      () =>
        new Response(
          new ReadableStream<Uint8Array>({
            async start(controller) {
              for (const frame of framesOf([{ event: 'start', id: 'ans-1' }, { event: 'statement', statement: STATEMENT }])) controller.enqueue(encoder.encode(frame));
              await new Promise<void>((resolve) => {
                finish = resolve;
              });
              for (const frame of answered().slice(2)) controller.enqueue(encoder.encode(frame));
              controller.close();
            },
          }),
        ),
    );
    renderPanel();
    ask();

    expect(await screen.findByText(STATEMENT.text)).toBeVisible();
    expect(screen.getByText('Answer being drafted by AI from inventory records only')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
    expect(screen.queryByRole('list', { name: 'Sources' })).toBeNull();

    finish();
    expect(await screen.findByRole('list', { name: 'Sources' })).toBeVisible();
  });

  it('renders the answer: AI label with basis and "as of", numbered citations to the obligation, and the pending change', async () => {
    serve();
    stubFetch(() => sseResponse(answered()));
    renderPanel();
    ask();

    expect(await screen.findByText('Answer drafted by AI from inventory records only, as of 1 Jun 2026')).toBeVisible();
    const statements = document.querySelectorAll('[data-ask-statement]');
    expect(statements).toHaveLength(2);
    expect(within(statements[0] as HTMLElement).getByText('1', { selector: 'sup' })).toBeVisible();
    expect(within(statements[0] as HTMLElement).queryByText(/Change pending/)).toBeNull();
    const pill = within(statements[1] as HTMLElement).getByText('Change pending: 1 Oct 2026');
    expect(pill).toHaveAttribute('data-pill', 'warning');

    const sources = within(screen.getByRole('list', { name: 'Sources' })).getAllByRole('link');
    expect(sources.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['FFFS 2017:2, 9 kap. 10 §, version 1', '/inventory/obligations/ob-1'],
      ['FFFS 2017:2, 9 kap. 6 §, version 2', '/inventory/obligations/ob-2'],
    ]);
    expect(screen.queryByText(/cut short/)).toBeNull();
  });

  it('says an answer that stopped at the length limit was cut short', async () => {
    serve();
    stubFetch(() => sseResponse(answered({}, 'max_tokens')));
    renderPanel();
    ask();
    expect(await screen.findByText('This answer was cut short at its length limit. Ask a narrower question for the rest.')).toBeVisible();
  });

  it('says there is no answer, guesses nothing, and offers to search instead with the question', async () => {
    serve();
    stubFetch(() => sseResponse(framesOf([{ event: 'start', id: 'ans-1' }, { event: 'answer', answer: answer({ statements: [], citations: [], noAnswer: true }), stopReason: null }])));
    renderPanel();
    ask('Do we need a licence for crypto custody?');

    expect(await screen.findByRole('heading', { name: 'No answer in the inventory' })).toBeVisible();
    expect(document.querySelectorAll('[data-ask-statement]')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Helpful' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Search instead' }));
    expect(onSearchInstead).toHaveBeenCalledWith('Do we need a licence for crypto custody?');
  });

  it('says Ask is switched off, that search still works, and offers it', async () => {
    serve();
    stubFetch(() => new Response(JSON.stringify({ code: 'feature_off', detail: 'Your organisation has switched its AI features off.', status: 403 }), { status: 403 }));
    renderPanel();
    ask();

    expect(await screen.findByText('Ask is switched off for your organisation. Search still works.')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Search instead' }));
    expect(onSearchInstead).toHaveBeenCalledWith(QUESTION);
  });

  it('shows the restricted screen to a reader without the permission', async () => {
    serve();
    stubFetch(() => new Response(JSON.stringify({ code: 'permission_denied', detail: '', requiredPermission: 'search.use', status: 403 }), { status: 403 }));
    renderPanel();
    ask();
    expect(await screen.findByRole('heading', { name: 'This page is not available to you' })).toBeVisible();
    expect(screen.getByText('Needs search use')).toBeVisible();
  });

  it('shows a refusal such as the rate limit in the server\'s own words', async () => {
    serve();
    stubFetch(() => new Response(JSON.stringify({ code: 'rate_limited', detail: 'Too many questions. Wait a minute.', status: 429 }), { status: 429 }));
    renderPanel();
    ask();
    expect(await screen.findByText('Too many questions. Wait a minute.')).toBeVisible();
  });

  it('shows the error state when the server fails, and asks again on retry', async () => {
    serve();
    let calls = 0;
    const requests = stubFetch(() => {
      calls += 1;
      return calls === 1 ? new Response('{}', { status: 500 }) : sseResponse(answered());
    });
    renderPanel();
    ask();

    expect(await screen.findByRole('heading', { name: 'Ask is not answering' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(STATEMENT.text)).toBeVisible();
    expect(await requests[1]?.json()).toEqual({ question: QUESTION });
  });

  it('shows the error state when the stream ends on a problem', async () => {
    serve();
    stubFetch(() => sseResponse(framesOf([{ event: 'start', id: 'ans-1' }, { event: 'problem', code: 'model_unavailable', detail: 'The answer could not be finished. Ask again in a moment.' }])));
    renderPanel();
    ask();
    expect(await screen.findByRole('heading', { name: 'Ask is not answering' })).toBeVisible();
  });
});

describe('AskPanel feedback', () => {
  async function answeredPanel(script?: (sent: Sent) => Answer): Promise<Sent[]> {
    const sent = serve(script);
    stubFetch(() => sseResponse(answered()));
    renderPanel();
    ask();
    await screen.findByRole('list', { name: 'Sources' });
    return sent;
  }

  it('posts Helpful and confirms it', async () => {
    const sent = await answeredPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Helpful' }));

    expect(await screen.findByText('Thank you. Your feedback is logged with the answer.')).toBeVisible();
    const rated = sent.find((call) => call.path === '/api/v1/answers/ans-1/feedback');
    expect(rated?.body).toEqual({ feedback: 'helpful', note: '' });
  });

  it('asks what is wrong before sending Wrong, and can be cancelled', async () => {
    const sent = await answeredPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Wrong' }));

    const reason = screen.getByRole('textbox', { name: 'What is wrong?' });
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(reason).not.toBeInTheDocument();
    expect(sent.some((call) => call.path.endsWith('/feedback'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Wrong' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'What is wrong?' }), { target: { value: '  It misses the exemption.  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Thank you. Your feedback is logged with the answer.')).toBeVisible();
    expect(sent.find((call) => call.path === '/api/v1/answers/ans-1/feedback')?.body).toEqual({ feedback: 'wrong', note: 'It misses the exemption.' });
  });

  it('shows why a verdict was refused and keeps the buttons', async () => {
    await answeredPanel(() => ({ status: 501, data: { code: 'not_built', detail: 'Rating an answer is not switched on yet.', status: 501 } }));
    fireEvent.click(screen.getByRole('button', { name: 'Helpful' }));

    expect(await screen.findByText('Rating an answer is not switched on yet.')).toBeVisible();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Helpful' })).toBeEnabled());
  });

  it('offers a fresh verdict on the next answer', async () => {
    serve();
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      return sseResponse(calls === 1 ? answered() : framesOf([{ event: 'start', id: 'ans-2' }, { event: 'statement', statement: STATEMENT }, { event: 'answer', answer: answer({ id: 'ans-2', statements: [STATEMENT] }), stopReason: 'end_turn' }]));
    });
    renderPanel();
    ask();
    fireEvent.click(await screen.findByRole('button', { name: 'Helpful' }));
    await screen.findByText('Thank you. Your feedback is logged with the answer.');

    ask('And afterwards?');
    await waitFor(() => expect(document.querySelectorAll('[data-ask-statement]')).toHaveLength(1));
    expect(await screen.findByRole('button', { name: 'Helpful' })).toBeEnabled();
    expect(screen.queryByText('Thank you. Your feedback is logged with the answer.')).toBeNull();
  });
});
