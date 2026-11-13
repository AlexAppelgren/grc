import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminIndexScreen } from '@/components/admin/AdminIndexScreen';
import { AdminTabs } from '@/components/admin/AdminTabs';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';

const nav = vi.hoisted(() => ({ pathname: '/admin/members', replace: vi.fn() }));
const framed = vi.hoisted(() => ({ value: false }));
vi.mock('@/features/demo/use-demo-frame', async (importOriginal) => ({ ...(await importOriginal<object>()), useDemoFrame: () => framed.value }));
vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
}));

function open(permissions: readonly string[] | null, ui = <AdminTabs />) {
  return render(
    <PermissionsProvider permissions={permissions}>
      <LocaleProvider locale="en">{ui}</LocaleProvider>
    </PermissionsProvider>,
  );
}

const groups = () => within(screen.getByRole('navigation', { name: 'Admin sections' }));
const pages = () => within(screen.getByRole('navigation', { name: 'Pages in this section' }));

describe("Admin's tab bar (D-137)", () => {
  beforeEach(() => {
    nav.pathname = '/admin/members';
    nav.replace.mockReset();
    framed.value = false;
  });

  it('shows no tab bar in the public demo, whose recordings open no page of Admin a tab leads to', () => {
    framed.value = true;
    nav.pathname = '/admin/licences';
    const { container } = open(['members.manage', 'roles.manage', 'audit.read', 'ai_log.read']);
    expect(container).toBeEmptyDOMElement();
  });

  it('offers the groups the permissions unlock, each opening its first page, and the pages of the current group', () => {
    open(['members.manage', 'roles.manage', 'audit.read', 'ai_log.read']);
    expect(groups().getAllByRole('link').map((a) => a.textContent)).toEqual(['People', 'Organisation', 'Security', 'Logs']);
    expect(groups().getByRole('link', { name: 'People' })).toHaveAttribute('aria-current', 'page');
    expect(groups().getByRole('link', { name: 'Logs' })).toHaveAttribute('href', '/admin/audit-log');
    expect(pages().getAllByRole('link').map((a) => a.textContent)).toEqual(['Members', 'Roles']);
    expect(pages().getByRole('link', { name: 'Members' })).toHaveAttribute('aria-current', 'page');
  });

  it('marks the deepest matching page, so a sub-page keeps its tab', () => {
    nav.pathname = '/admin/agents/access/e1';
    open(['watch.read', 'agent_access.manage', 'integrations.manage']);
    expect(groups().getByRole('link', { name: 'Agents and keys' })).toHaveAttribute('aria-current', 'page');
    expect(pages().getByRole('link', { name: 'Agent access' })).toHaveAttribute('aria-current', 'page');
    expect(pages().getByRole('link', { name: 'Agents' })).not.toHaveAttribute('aria-current');
  });

  it('offers Agent access only to agent_access.manage', () => {
    nav.pathname = '/admin/agents';
    open(['watch.read']);
    expect(pages().getAllByRole('link').map((a) => a.textContent)).toEqual(['Agents']);
  });

  it('offers Licences to any member, second in Organisation', () => {
    nav.pathname = '/admin/licences';
    open(['audit.read']);
    expect(groups().getByRole('link', { name: 'Organisation' })).toHaveAttribute('aria-current', 'page');
    expect(pages().getAllByRole('link').map((a) => a.textContent)).toEqual(['Organisation', 'Licences']);
    expect(pages().getByRole('link', { name: 'Licences' })).toHaveAttribute('aria-current', 'page');
  });

  it('shows the groups without a current one on a page the person may not open', () => {
    nav.pathname = '/admin/members';
    open(['audit.read']);
    expect(groups().getAllByRole('link').map((a) => a.textContent)).toEqual(['Organisation', 'Security', 'Logs']);
    expect(groups().queryByRole('link', { current: 'page' })).toBeNull();
    expect(screen.queryByRole('navigation', { name: 'Pages in this section' })).toBeNull();
  });

  it('sends /admin to the first page the person may open', () => {
    open(['audit.read'], <AdminIndexScreen />);
    expect(nav.replace).toHaveBeenCalledWith('/admin/organisation');
    nav.replace.mockReset();
    open(['members.manage', 'audit.read'], <AdminIndexScreen />);
    expect(nav.replace).toHaveBeenCalledWith('/admin/members');
  });

  it('waits for the session before it sends anyone anywhere', () => {
    open(null, <AdminIndexScreen />);
    expect(nav.replace).not.toHaveBeenCalled();
  });
});
