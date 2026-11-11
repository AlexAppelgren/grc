import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SupportSessionBanner } from '@/components/shell/SupportSessionBanner';
import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { renderWith } from '@/shared/testing/render';

// A support session's banner and the page it meets when its grant ends
// (TEN-06, D-49): the bank named, read-only said, and a way out.

beforeEach(() => {
  resetApiForTests();
  installAdapter(() => ({ status: 401, data: { code: 'unauthenticated', detail: 'Not for this test.' } }));
});

describe('the support session banner', () => {
  it('names the bank, says it only reads until when, and leaves', () => {
    const onLeave = vi.fn();
    renderWith(<SupportSessionBanner tenantName="Example Bank AB" endsAt="2026-09-25T09:14:00Z" onLeave={onLeave} />);
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Support access to Example Bank AB.');
    expect(banner).toHaveTextContent(/Read only, until .+\./);
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

});
