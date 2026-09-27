import { act, render, screen, within } from '@testing-library/react';
import { Suspense, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import ConsoleAgentsPage from '@/app/(console)/console/agents/page';
import { AgentDefinitionsScreen } from '@/components/console/AgentDefinitionsScreen';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// The console's agent definitions (AGT-03, ADM-02): every agent bleqq ships
// with its scope, version and state, each opening on its own page; and the
// loading, empty, error and denied states the card draws.

const DEFINITIONS_PATH = '/api/v1/agent-definitions';

const definition = (key: string, extra: Record<string, unknown> = {}) => ({
  id: `id-${key}`,
  key,
  description: `What ${key} does.`,
  currentVersion: 3,
  active: true,
  scope: 'platform',
  tenantConfigurable: false,
  publishedAt: '2026-09-21T07:12:00Z',
  ...extra,
});

function server(answer: Answer) {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === DEFINITIONS_PATH) return answer;
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderIn(node: ReactNode) {
  const { wrapper: Query } = queryWrapper();
  return render(<Query>{node}</Query>);
}

describe('console agent definitions', () => {
  beforeEach(() => resetApiForTests());

  it('lists each definition with its pills, its key and a link to its page', async () => {
    const sent = server({
      status: 200,
      data: { items: [definition('watch-sweeper'), definition('topic-research', { scope: 'tenant', active: false, publishedAt: null, currentVersion: 1 })], total: 2 },
    });
    renderIn(<AgentDefinitionsScreen />);

    expect(await screen.findByRole('link', { name: 'Watch sweeper' })).toHaveAttribute('href', '/console/agents/watch-sweeper');
    const sweeper = document.querySelector('[data-agent-definition="watch-sweeper"]') as HTMLElement;
    expect(within(sweeper).getByText('Platform')).toHaveAttribute('data-pill', 'information');
    expect(within(sweeper).getByText('Version 3')).toHaveAttribute('data-pill', 'brand');
    expect(within(sweeper).getByText('Active')).toHaveAttribute('data-pill', 'positive');
    expect(within(sweeper).getByText('What watch-sweeper does.')).toBeInTheDocument();
    expect(within(sweeper).getByText(/^Published /)).toBeInTheDocument();

    const draft = document.querySelector('[data-agent-definition="topic-research"]') as HTMLElement;
    expect(within(draft).getByText('For banks')).toHaveAttribute('data-pill', 'information');
    expect(within(draft).getByText('Draft')).toHaveAttribute('data-pill', 'information');
    expect(within(draft).queryByText('Version 1')).toBeNull();
    expect(within(draft).getByText('No version published yet')).toBeInTheDocument();
    expect(sent.find((s) => s.path === DEFINITIONS_PATH)?.params).toEqual({ limit: 100, offset: 0 });
  });

  it('says so when no definition is loaded yet', async () => {
    server({ status: 200, data: { items: [], total: 0 } });
    renderIn(<AgentDefinitionsScreen />);
    expect(await screen.findByText('No agent definitions yet')).toBeInTheDocument();
  });

  it('offers a retry when the list cannot be read', async () => {
    server({ status: 500, data: { code: 'server_error', detail: 'Down.' } });
    renderIn(<AgentDefinitionsScreen />);
    expect(await screen.findByText('Could not load the agent definitions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('refuses a person without agent definitions manage before any request is made', async () => {
    const sent = server({ status: 200, data: { items: [definition('watch-sweeper')], total: 1 } });
    const { wrapper: Query } = queryWrapper();
    await act(async () => {
      render(
        <Query>
          <Suspense fallback={null}>
            <PermissionsProvider permissions={['proposals.review']}>
              <ConsoleAgentsPage />
            </PermissionsProvider>
          </Suspense>
        </Query>,
      );
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Needs agent definitions manage');
    expect(sent.filter((s) => s.path === DEFINITIONS_PATH)).toEqual([]);
  });
});
