import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import ConsoleEvaluationPage from '@/app/(console)/console/evaluation/page';
import { EvaluationScreen } from '@/components/console/EvaluationScreen';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The console's evaluation page (SRC-05, ADM-02): the set filterable by
// language, the add form that says a new question is not yet in the release
// gate, the baseline that reads "Unrecorded" and never zero, and past runs.

const ME_PATH = '/api/v1/me';
const QUESTIONS_PATH = '/api/v1/eval/questions';
const RUNS_PATH = '/api/v1/eval/runs';
const BASELINE_PATH = '/api/v1/eval/baseline';
const LANGUAGES_PATH = '/api/v1/reference/languages';

const LANGUAGES = [
  { key: 'en', kind: null, label: 'English' },
  { key: 'sv', kind: null, label: 'Svenska' },
];

const question = (key: string, lang: string, extra: Record<string, unknown> = {}) => ({
  id: `id-${key}`,
  key,
  lang,
  question: `question ${key}`,
  expected: ['obl-costs-charges'],
  matchKind: 'keyword',
  asOf: null,
  notes: '',
  active: true,
  inGate: true,
  ...extra,
});

const EN = question('r-en-01', 'en', { question: 'FFFS 2017:2', notes: 'The identifier itself.' });
const SV = question('r-sv-01', 'sv', { question: 'kostnader och avgifter', matchKind: 'concept', inGate: false });
const RETIRED = question('r-en-02', 'en', { active: false, expected: [] });

const scores = (recallAt10: number, mrr: number) => ({ recallAt10, mrr });
const RUN = {
  id: 'run-1',
  runAt: '2026-09-20T08:00:00Z',
  config: { retriever: 'apps.search.eval:Retriever (embedder mock, reranker none)', isMock: true, questions: 53 },
  metrics: { overall: scores(0.5, 0.25), perLanguage: { en: scores(0.5, 0.25) }, perMatchKind: { keyword: scores(0.5, 0.25) } },
  results: [],
};
const UNRECORDED = { recorded: false, recordedAt: null, recallAt10: null, mrr: null };

const editor = {
  user: { id: 'u10', email: 'editor@bleqq.test', name: 'Ida Holm', locale: 'en' },
  tenant: null,
  roles: [],
  permissions: ['proposals.review', 'library_vocab.manage', 'sources.manage', 'eval.manage'],
  platformRoles: [{ key: 'library_editor', kind: null, label: 'Library editor' }],
  enrolmentPending: false,
  passkeyCount: 1,
  stepUpValidUntil: null,
};

interface Script {
  questions?: Answer;
  runs?: Answer;
  baseline?: Answer;
  create?: Answer;
}

function server(script: Script = {}): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ME_PATH) return { status: 200, data: editor };
    if (sent.path === LANGUAGES_PATH) return { status: 200, data: LANGUAGES };
    if (sent.path === QUESTIONS_PATH && sent.method === 'get') return script.questions ?? { status: 200, data: { items: [EN, SV, RETIRED], total: 3 } };
    if (sent.path === QUESTIONS_PATH && sent.method === 'post') return script.create ?? { status: 201, data: question('r-sv-90', 'sv', { inGate: false }) };
    if (sent.path === RUNS_PATH) return script.runs ?? { status: 200, data: { items: [RUN], total: 1 } };
    if (sent.path === BASELINE_PATH) return script.baseline ?? { status: 200, data: UNRECORDED };
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

const rowOf = (key: string) => document.querySelector(`[data-question-key="${key}"]`) as HTMLElement;
const keys = () => [...document.querySelectorAll('[data-question-key]')].map((el) => el.getAttribute('data-question-key'));
const baselineOf = (metric: string) => document.querySelector(`[data-baseline-metric="${metric}"] [data-baseline-value]`)?.textContent;

describe('console evaluation', () => {
  beforeEach(() => {
    resetApiForTests();
  });

  it('shows each question with whether the gate scores it, its language and how it should be found', async () => {
    server();
    renderIn(<EvaluationScreen />);
    await screen.findByText('FFFS 2017:2');

    const inGate = rowOf('r-en-01');
    expect(within(inGate).getByText('In the release gate')).toBeInTheDocument();
    expect(within(inGate).getByText('English')).toBeInTheDocument();
    expect(within(inGate).getByText('Keyword match')).toBeInTheDocument();
    expect(within(inGate).getByText('Expects obl-costs-charges')).toBeInTheDocument();
    expect(within(inGate).getByText('The identifier itself.')).toBeInTheDocument();

    expect(within(rowOf('r-sv-01')).getByText('Not yet in the release gate')).toBeInTheDocument();
    expect(within(rowOf('r-sv-01')).getByText('Concept match')).toBeInTheDocument();
    expect(within(rowOf('r-en-02')).getByText('Retired')).toBeInTheDocument();
    expect(within(rowOf('r-en-02')).getByText('Expects no answer')).toBeInTheDocument();
  });

  it('filters the set by language', async () => {
    server();
    renderIn(<EvaluationScreen />);
    await screen.findByText('FFFS 2017:2');
    expect(keys()).toEqual(['r-en-01', 'r-sv-01', 'r-en-02']);

    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'sv' } });
    await waitFor(() => expect(keys()).toEqual(['r-sv-01']));
    expect(screen.getByText('1 of 3 questions')).toBeInTheDocument();
  });

  it('reads every page of the set, so a filter never hides a question the server holds', async () => {
    const all = Array.from({ length: 101 }, (_, n) => question(`r-en-${n + 100}`, n === 100 ? 'sv' : 'en'));
    const sent = installAdapter((s) => {
      if (s.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
      if (s.path === ME_PATH) return { status: 200, data: editor };
      if (s.path === LANGUAGES_PATH) return { status: 200, data: LANGUAGES };
      if (s.path === QUESTIONS_PATH) {
        const { offset } = s.params as { offset: number };
        return { status: 200, data: { items: all.slice(offset, offset + 100), total: all.length } };
      }
      if (s.path === RUNS_PATH) return { status: 200, data: { items: [], total: 0 } };
      return { status: 200, data: UNRECORDED };
    });
    renderIn(<EvaluationScreen />);
    fireEvent.change(await screen.findByLabelText('Language'), { target: { value: 'sv' } });
    await waitFor(() => expect(keys()).toEqual(['r-en-200']));
    expect(sent.filter((s) => s.path === QUESTIONS_PATH).map((s) => s.params)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
  });

  it('reads an unrecorded baseline as Unrecorded, never as zero, beside the latest run', async () => {
    server();
    renderIn(<EvaluationScreen />);
    await screen.findByText('FFFS 2017:2');
    expect(baselineOf('recallAt10')).toBe('Unrecorded');
    expect(baselineOf('mrr')).toBe('Unrecorded');
    expect(screen.getByText('Nobody has recorded a baseline yet, so no build fails on these scores.')).toBeInTheDocument();
    expect(document.querySelector('[data-baseline-metric="recallAt10"] [data-latest-value]')?.textContent).toBe('0.50');
  });

  it('reads a recorded zero as a zero', async () => {
    server({ baseline: { status: 200, data: { recorded: true, recordedAt: '2026-09-20T08:00:00Z', recallAt10: 0, mrr: 0.8123 } } });
    renderIn(<EvaluationScreen />);
    await screen.findByText('FFFS 2017:2');
    expect(baselineOf('recallAt10')).toBe('0.00');
    expect(baselineOf('mrr')).toBe('0.812');
  });

  it('lists past runs, a stand-in run marked as one', async () => {
    server();
    renderIn(<EvaluationScreen />);
    const run = (await screen.findByText(RUN.config.retriever)).closest('[data-run-id]') as HTMLElement;
    expect(within(run).getByText('Stand-in models')).toBeInTheDocument();
    expect(within(run).getByText('53 questions')).toBeInTheDocument();
    expect(within(run).getByText('Recall at 10 0.50')).toBeInTheDocument();
    expect(screen.getByText('Showing 1 of 1 runs')).toBeInTheDocument();
  });

  it('says so when no run has been recorded and the set is empty', async () => {
    server({ questions: { status: 200, data: { items: [], total: 0 } }, runs: { status: 200, data: { items: [], total: 0 } } });
    renderIn(<EvaluationScreen />);
    expect(await screen.findByText('No questions yet')).toBeInTheDocument();
    expect(screen.getByText('No runs recorded yet')).toBeInTheDocument();
    expect(baselineOf('mrr')).toBe('Unrecorded');
    expect(document.querySelector('[data-baseline-metric="mrr"] [data-latest-value]')?.textContent).toBe('No run yet');
  });

  it('adds a question, saying first and after that it is not yet in the release gate', async () => {
    const sent = server();
    renderIn(<EvaluationScreen />);
    await screen.findByText('FFFS 2017:2');
    fireEvent.click(screen.getByRole('button', { name: 'Add a question' }));
    const form = await screen.findByRole('dialog', { name: 'Add a question' });
    expect(within(form).getByText(/^Not yet in the release gate\./)).toBeInTheDocument();

    fireEvent.click(within(form).getByRole('button', { name: 'Add question' }));
    expect(await within(form).findByText('Give the question a key.')).toBeInTheDocument();
    expect(sent.some((s) => s.method === 'post' && s.path === QUESTIONS_PATH)).toBe(false);

    fireEvent.change(within(form).getByLabelText('Key'), { target: { value: ' r-sv-90 ' } });
    await waitFor(() => expect(within(form).getByRole('option', { name: 'Svenska' })).toBeInTheDocument());
    fireEvent.change(within(form).getByLabelText('Language'), { target: { value: 'sv' } });
    fireEvent.change(within(form).getByLabelText('Question'), { target: { value: 'kostnader och avgifter före tjänsten' } });
    fireEvent.change(within(form).getByLabelText('Expected records'), { target: { value: 'obl-costs-charges\nobl-other, obl-third' } });
    fireEvent.change(within(form).getByLabelText('Should be found by'), { target: { value: 'both' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Add question' }));

    expect(await screen.findByText('Added r-sv-90. It is not yet in the release gate.')).toBeInTheDocument();
    const post = sent.find((s) => s.method === 'post' && s.path === QUESTIONS_PATH);
    expect(post?.body).toEqual({
      key: 'r-sv-90',
      lang: 'sv',
      question: 'kostnader och avgifter före tjänsten',
      expected: ['obl-costs-charges', 'obl-other', 'obl-third'],
      matchKind: 'both',
      notes: '',
    });
  });

  it('says a taken key is taken, and keeps the form open', async () => {
    server({ create: { status: 409, data: { code: 'duplicate_key', detail: 'Taken.', status: 409, title: 'Conflict' } } });
    renderIn(<EvaluationScreen />);
    await screen.findByText('FFFS 2017:2');
    fireEvent.click(screen.getByRole('button', { name: 'Add a question' }));
    const form = await screen.findByRole('dialog', { name: 'Add a question' });
    fireEvent.change(within(form).getByLabelText('Key'), { target: { value: 'r-en-01' } });
    await waitFor(() => expect(within(form).getByRole('option', { name: 'English' })).toBeInTheDocument());
    fireEvent.change(within(form).getByLabelText('Language'), { target: { value: 'en' } });
    fireEvent.change(within(form).getByLabelText('Question'), { target: { value: 'again' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Add question' }));
    expect(await within(form).findByText('The set already has a question with that key. Keys are never reused.')).toBeInTheDocument();
  });

  it('offers a retry when the set could not be read', async () => {
    server({ baseline: { status: 500, data: { code: 'server_error', detail: 'no' } } });
    renderIn(<EvaluationScreen />);
    expect(await screen.findByText('Could not load the evaluation set')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('is loading until every read has answered', () => {
    server();
    const { container } = renderIn(<EvaluationScreen />);
    expect(container.querySelector('[data-loading-state]')).not.toBeNull();
  });

  it('shows the Restricted screen, naming the grant, to a console session without eval.manage', async () => {
    server();
    renderIn(
      <PermissionsProvider permissions={['tenants.manage', 'agent_definitions.manage']}>
        <ConsoleEvaluationPage />
      </PermissionsProvider>,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Needs eval manage');
  });
});
