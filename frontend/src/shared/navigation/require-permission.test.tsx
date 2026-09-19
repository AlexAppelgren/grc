import { render, screen } from '@testing-library/react';
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it, vi } from 'vitest';

import { forbiddenFrom, humanisePermission, PermissionsProvider, RequirePermission, RestrictedScreen } from './require-permission';

function axios403(data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const response = { status: 403, data, statusText: 'Forbidden', headers: {}, config } as AxiosResponse;
  return new AxiosError('forbidden', '403', config, undefined, response);
}

function Throws({ error }: { error: unknown }): never {
  throw error;
}

describe('forbiddenFrom', () => {
  it('reads the structured 403 body', () => {
    expect(forbiddenFrom(axios403({ detail: 'Only an approver may sign off', code: 'permission_denied', requiredPermission: 'cases.signoff' }))).toEqual({
      detail: 'Only an approver may sign off',
      code: 'permission_denied',
      requiredPermission: 'cases.signoff',
    });
    expect(forbiddenFrom(axios403('nope'))).toEqual({ detail: '', code: 'forbidden' });
    expect(forbiddenFrom(axios403({}))).toEqual({ detail: '', code: 'forbidden', requiredPermission: undefined });
  });

  it('ignores anything that is not a 403', () => {
    expect(forbiddenFrom(new Error('x'))).toBeNull();
    const config = { headers: {} } as InternalAxiosRequestConfig;
    const notFound = new AxiosError('nf', '404', config, undefined, { status: 404, data: {}, statusText: '', headers: {}, config } as AxiosResponse);
    expect(forbiddenFrom(notFound)).toBeNull();
  });

  it('humanises a grant name', () => {
    expect(humanisePermission('cases.signoff')).toBe('cases signoff');
    expect(humanisePermission('library_vocab.manage')).toBe('library vocab manage');
  });
});

describe('RequirePermission', () => {
  it('renders children when a permission unlocks', () => {
    render(
      <PermissionsProvider permissions={['watch.read']}>
        <RequirePermission anyOf={['watch.read', 'library.read']}>
          <p>inside</p>
        </RequirePermission>
      </PermissionsProvider>,
    );
    expect(screen.getByText('inside')).toBeInTheDocument();
  });

  it('renders the quiet Restricted screen with the humanised grant otherwise', () => {
    render(
      <PermissionsProvider permissions={[]}>
        <RequirePermission anyOf={['cases.signoff']}>
          <p>inside</p>
        </RequirePermission>
      </PermissionsProvider>,
    );
    expect(screen.queryByText('inside')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('This page is not available to you');
    expect(screen.getByRole('alert')).toHaveTextContent('Needs cases signoff');
  });

  it('treats no session as no permissions', () => {
    render(
      <RequirePermission anyOf={['watch.read']}>
        <p>inside</p>
      </RequirePermission>,
    );
    expect(screen.queryByText('inside')).not.toBeInTheDocument();
  });

  it('renders a server 403 thrown below it as the same screen with the server detail', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(
      <PermissionsProvider permissions={['watch.read']}>
        <RequirePermission anyOf={['watch.read']}>
          <Throws error={axios403({ detail: 'Only an approver may sign off', code: 'permission_denied', requiredPermission: 'cases.signoff' })} />
        </RequirePermission>
      </PermissionsProvider>,
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Only an approver may sign off');
    expect(alert).toHaveTextContent('Needs cases signoff');
    expect(alert).toHaveTextContent('Reference permission_denied');
    spy.mockRestore();
  });

  it('rethrows anything that is not a 403', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() =>
      render(
        <PermissionsProvider permissions={['watch.read']}>
          <RequirePermission anyOf={['watch.read']}>
            <Throws error={new Error('boom')} />
          </RequirePermission>
        </PermissionsProvider>,
      ),
    ).toThrow('boom');
    spy.mockRestore();
  });
});

describe('RestrictedScreen', () => {
  it('falls back to catalog copy when the server sends no detail', () => {
    render(<RestrictedScreen detail="" code="forbidden" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Your role does not include what this page needs');
    expect(screen.getByRole('alert')).toHaveTextContent('Reference forbidden');
  });
});
