import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SupportAccessEnded, SupportSessionBanner } from '@/components/shell/SupportSessionBanner';
import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// A support session's banner and the page it meets when its grant ends
// (TEN-06, D-49): the bank named, read-only said, and a way out.

beforeEach(() => {
  resetApiForTests();
  installAdapter((sent) => (sent.path === REFRESH_PATH ? { status: 200, data: { accessToken: 'tok' } } : { status: 401, data: { code: 'unauthenticated', detail: 'Not for this test.' } }));
});

describe('the support session banner', () => {
  it('names the bank, says it only reads until when, and leaves', () => {
    const onLeave = vi.fn();
    const { wrapper: Query } = queryWrapper();
    render(
      <Query>
        <SupportSessionBanner tenantName="Example Bank AB" endsAt="2026-09-25T09:14:00Z" onLeave={onLeave} />
      </Query>,
    );
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Support access to Example Bank AB.');
    expect(banner).toHaveTextContent(/Read only, until .+\./);
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it('ends with the bank named and a way back to the console', () => {
    render(<SupportAccessEnded tenantName="Example Bank AB" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Support access has ended');
    expect(screen.getByText('Example Bank AB revoked the access, or its window closed. Nothing more can be read.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to the console' })).toHaveAttribute('href', '/console');
  });
});
