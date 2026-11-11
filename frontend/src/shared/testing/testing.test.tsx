import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { api, REFRESH_PATH } from '@/shared/utils/api-client';

import { installAdapter, resetApiForTests } from './api-adapter';
import { session } from './fixtures';
import { renderWith } from './render';

// The test support itself: the adapter answers a signed-in session by
// default, and renderWith wraps a node the way the app does.

function Probe() {
  const t = useT();
  const permissions = usePermissions();
  return <p>{`${t('common.cancel')} ${permissions === null ? 'session' : permissions.join(',')}`}</p>;
}

describe('installAdapter', () => {
  beforeEach(() => resetApiForTests());

  it('answers the refresh with a token and GET /me with the given session before asking the script', async () => {
    const asked: string[] = [];
    installAdapter((s) => {
      asked.push(s.path);
      return { status: 404 };
    }, { me: session(['watch.read']) });
    expect((await api.post(REFRESH_PATH)).data).toEqual({ accessToken: 'tok' });
    expect((await api.get('/api/v1/me')).data).toEqual(session(['watch.read']));
    await expect(api.get('/api/v1/changes')).rejects.toThrow();
    expect(asked).toEqual(['/api/v1/changes']);
  });

  it('leaves the refresh to the script when the test scripts the session itself', async () => {
    installAdapter((s) => (s.path === REFRESH_PATH ? { status: 401 } : { status: 200 }), { refresh: false });
    await expect(api.post(REFRESH_PATH)).rejects.toThrow();
  });
});

describe('renderWith', () => {
  it('renders in English with the session’s permissions unless the test names them', () => {
    renderWith(<Probe />);
    expect(screen.getByText('Cancel session')).toBeInTheDocument();
  });

  it('renders in the given locale and permissions', () => {
    renderWith(<Probe />, { locale: 'sv', permissions: ['cases.read'] });
    expect(screen.getByText('Avbryt cases.read')).toBeInTheDocument();
  });
});
