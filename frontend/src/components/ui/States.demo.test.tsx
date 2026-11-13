import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ErrorState, NotFoundScreen, QueryState } from './States';

// Inside the public page's demo, a read with no recording reads the demo's line
// wherever a screen would have said "not found" or "check your connection".
vi.mock('@/features/demo/frame', async (importOriginal) => ({ ...(await importOriginal<object>()), useDemoFrame: () => true }));

const DEMO_LINE = 'The demo has no sample data for this page.';

function Failing() {
  const query = useQuery({
    queryKey: ['unrecorded'],
    queryFn: (): Promise<string> => Promise.reject(new Error('demo_not_recorded')),
    retry: false,
  });
  return (
    <QueryState query={query} errorTitle="Could not load the list">
      {(data) => data}
    </QueryState>
  );
}

describe('the states in the demo', () => {
  it('not found reads the demo line and leads back to Today, whatever the screen passed', () => {
    render(<NotFoundScreen body="This bank was never sent a briefing for that week." backHref="/briefing" backLabel="See the current one" />);
    expect(screen.getByRole('heading', { name: DEMO_LINE })).toBeInTheDocument();
    expect(screen.queryByText('Not found')).not.toBeInTheDocument();
    expect(screen.queryByText('This bank was never sent a briefing for that week.')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to Today' })).toHaveAttribute('href', '/');
  });

  it('an error reads the demo line and offers no retry', () => {
    render(<ErrorState title="Could not load the regulation" onRetry={() => undefined} />);
    expect(screen.getByRole('alert')).toHaveTextContent(`Could not load the regulation${DEMO_LINE}`);
    expect(screen.queryByText('Check your connection and try again.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('a read that fails under QueryState reads the demo line', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Failing />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(DEMO_LINE);
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });
});
