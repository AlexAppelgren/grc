import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

import { AuthFrame } from './AuthFrame';

describe('AuthFrame', () => {
  it('says what the service is and who runs it under the panel, with the privacy and security contacts', () => {
    render(
      <LocaleProvider locale="en">
        <AuthFrame>
          <p>panel</p>
        </AuthFrame>
      </LocaleProvider>,
    );
    expect(within(screen.getByRole('main')).getByText('panel')).toBeInTheDocument();
    const about = screen.getByRole('contentinfo', { name: 'About this service' });
    expect(within(about).getByText(/keeps a bank's regulatory obligations in one inventory/)).toBeInTheDocument();
    // A plain link to the public page, which the server moves to the public host when the app has its own.
    expect(within(about).getByRole('link', { name: 'bleqq' })).toHaveAttribute('href', '/welcome');
    expect(within(about).getByRole('link', { name: 'privacy@bleqq.com' })).toHaveAttribute('href', 'mailto:privacy@bleqq.com');
    expect(within(about).getByRole('link', { name: 'security@bleqq.com' })).toHaveAttribute('href', 'mailto:security@bleqq.com');
  });
});
