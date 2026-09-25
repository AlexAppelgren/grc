import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { AdminGate } from '@/components/admin/AdminGate';
import { WorkflowPolicyScreen } from '@/features/workflow-policy/WorkflowPolicyScreen';
import { childDestinations } from '@/shared/navigation/registry';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { REFRESH_PATH } from '@/shared/utils/api-client';

// /admin/workflow (COL-02, TEN-01): each field shows its unit and the platform
// default, the whole policy saves through PATCH /tenant/workflow, a 422 lands
// under the field it names by its code, and without workflow.manage the page
// is restricted and has no entry under Admin.

const TENANT_PATH = '/api/v1/tenant';
const ROLES_PATH = '/api/v1/tenant/roles';
const WORKFLOW_PATH = '/api/v1/tenant/workflow';

const officer = { key: 'compliance_officer', kind: null, label: 'Compliance officer' };
const admin = { key: 'admin', kind: null, label: 'Administrator' };
const headOfRisk = { key: 'head_of_risk', kind: null, label: 'Head of risk' };
const role = (ref: typeof officer) => ({ ...ref, active: true, isSystem: ref.key !== 'head_of_risk', labels: {}, permissions: [], usageNote: null });

const defaults = { reminderDaysBefore: [3], reviewReminderDaysBefore: [30], escalateAfterDays: 5, escalateToRole: officer, digestWeekday: 'monday', triageTargetHours: 48 };
const tenant = {
  id: 'ta',
  name: 'Example Bank AB',
  slug: 'example-bank',
  timezone: 'Europe/Stockholm',
  status: 'active',
  defaultLanguage: null,
  contentLanguages: [],
  aiEnabled: true,
  onboarding: { stepsDone: 0, steps: [] },
  workflow: { ...defaults, reminderDaysBefore: [7, 3], escalateAfterDays: 10 },
  workflowDefaults: defaults,
};

function server(patch: (sent: Sent) => Answer = (sent) => ({ status: 200, data: { ...tenant, workflow: { ...tenant.workflow, ...(sent.body as object), escalateToRole: officer } } })): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === REFRESH_PATH) return { status: 200, data: { accessToken: 'tok' } };
    if (sent.path === ROLES_PATH) return { status: 200, data: [role(admin), role(officer), role(headOfRisk)] };
    if (sent.path === TENANT_PATH && sent.method === 'get') return { status: 200, data: tenant };
    if (sent.path === WORKFLOW_PATH && sent.method === 'patch') return patch(sent);
    return { status: 404, data: { code: 'not_found', detail: 'Not for this test.' } };
  });
}

const patches = (sent: Sent[]) => sent.filter((s) => s.method === 'patch' && s.path === WORKFLOW_PATH).map((s) => s.body);

async function renderScreen(permissions: readonly string[] = ['workflow.manage']): Promise<void> {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <PermissionsProvider permissions={permissions}>
        <AdminGate id="admin-workflow">
          <WorkflowPolicyScreen />
        </AdminGate>
      </PermissionsProvider>
    </Query>,
  );
  if (permissions.includes('workflow.manage')) await screen.findByLabelText('Escalate after');
}

const field = (name: string) => document.querySelector(`[data-workflow-field="${name}"]`) as HTMLElement;

beforeEach(() => {
  resetApiForTests();
});

describe('the workflow policy page', () => {
  it('shows each field with its unit and the platform default beside it', async () => {
    server();
    await renderScreen();
    expect(within(field('reminderDaysBefore')).getByText('7 days')).toBeInTheDocument();
    expect(within(field('reminderDaysBefore')).getByText('Days before. Up to 5 reminders, each 1 to 90 days. Platform default: 3 days.')).toBeInTheDocument();
    // The last reminder in a list has no remove button: the server refuses an empty list.
    expect(within(field('reviewReminderDaysBefore')).queryByRole('button', { name: /Remove/ })).toBeNull();
    expect(within(field('reviewReminderDaysBefore')).getByText(/Platform default: 30 days\.$/)).toBeInTheDocument();
    expect(screen.getByLabelText('Escalate after')).toHaveValue(10);
    expect(within(field('escalateAfterDays')).getByText('days overdue')).toBeInTheDocument();
    expect(within(field('escalateAfterDays')).getByText('1 to 90 days. Platform default: 5 days.')).toBeInTheDocument();
    expect(screen.getByLabelText('Escalate to')).toHaveValue('compliance_officer');
    expect(within(field('escalateToRole')).getByText(/Platform default: Compliance officer\.$/)).toBeInTheDocument();
    expect(within(field('digestWeekday')).getByText("In the morning, in your organisation's timezone (Europe/Stockholm). Platform default: Monday.")).toBeInTheDocument();
    expect(within(field('triageTargetHours')).getByText('hours')).toBeInTheDocument();
    expect(within(field('triageTargetHours')).getByText('1 to 720 hours. Platform default: 48 hours.')).toBeInTheDocument();
  });

  it('saves the whole policy as keys and shows the saved state', async () => {
    const sent = server();
    await renderScreen();
    fireEvent.change(screen.getByLabelText('Days before a due date'), { target: { value: '14' } });
    fireEvent.click(within(field('reminderDaysBefore')).getByRole('button', { name: 'Add' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove 3 days' }));
    fireEvent.change(screen.getByLabelText('Escalate to'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Send the weekly digest on'), { target: { value: 'thursday' } });
    fireEvent.change(screen.getByLabelText('Triage new changes within'), { target: { value: '72' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Saved.');
    expect(patches(sent)).toEqual([
      { reminderDaysBefore: [14, 7], reviewReminderDaysBefore: [30], escalateAfterDays: 10, escalateToRole: 'admin', digestWeekday: 'thursday', triageTargetHours: 72 },
    ]);
  });

  it('refuses before sending: a number out of range, a day already listed, a full list', async () => {
    const sent = server();
    await renderScreen();
    fireEvent.change(screen.getByLabelText('Escalate after'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await within(field('escalateAfterDays')).findByRole('alert')).toHaveTextContent('Enter a whole number from 1 to 90.');
    expect(screen.getByLabelText('Escalate after')).toHaveAttribute('aria-invalid', 'true');

    fireEvent.change(screen.getByLabelText('Days before a review'), { target: { value: '30' } });
    fireEvent.click(within(field('reviewReminderDaysBefore')).getByRole('button', { name: 'Add' }));
    expect(within(field('reviewReminderDaysBefore')).getByRole('alert')).toHaveTextContent('30 days is already in the list.');

    for (const day of ['30', '14', '1']) {
      fireEvent.change(screen.getByLabelText('Days before a due date'), { target: { value: day } });
      fireEvent.keyDown(screen.getByLabelText('Days before a due date'), { key: 'Enter' });
    }
    expect(screen.getByLabelText('Days before a due date')).toBeDisabled();
    expect(within(field('reminderDaysBefore')).getByText('Up to 5 reminders. Remove one to add another.')).toBeInTheDocument();
    expect(patches(sent)).toEqual([]);
  });

  it('fills the form with the platform defaults on reset and saves nothing until Save', async () => {
    const sent = server();
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Reset to platform defaults' }));
    expect(screen.getByLabelText('Escalate after')).toHaveValue(5);
    expect(within(field('reminderDaysBefore')).queryByText('7 days')).toBeNull();
    expect(patches(sent)).toEqual([]);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Saved.');
    expect(patches(sent)).toEqual([{ reminderDaysBefore: [3], reviewReminderDaysBefore: [30], escalateAfterDays: 5, escalateToRole: 'compliance_officer', digestWeekday: 'monday', triageTargetHours: 48 }]);
  });

  it("renders the server's 422 under the field it names, chosen by its code", async () => {
    server(() => ({ status: 422, data: { code: 'unknown_key', detail: 'Pick one of your organisation roles.', status: 422, errors: [{ field: 'escalateToRole', message: 'Pick one.' }] } }));
    await renderScreen();
    fireEvent.change(screen.getByLabelText('Escalate to'), { target: { value: 'head_of_risk' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await within(field('escalateToRole')).findByRole('alert')).toHaveTextContent('That role no longer exists. Choose another.');
    expect(screen.getByLabelText('Escalate to')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByText('Pick one of your organisation roles.')).toBeNull();
  });

  it('renders a validation_error under the field it names', async () => {
    server(() => ({ status: 422, data: { code: 'validation_error', detail: 'Some fields need attention.', status: 422, errors: [{ field: 'body.triageTargetHours', message: 'too big' }] } }));
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await within(field('triageTargetHours')).findByRole('alert')).toHaveTextContent('Enter a whole number from 1 to 720.');
  });

  it('renders a lost permission in place, naming it', async () => {
    server(() => ({ status: 403, data: { code: 'permission_denied', detail: 'You do not have permission to do this.', status: 403, requiredPermission: 'workflow.manage' } }));
    await renderScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(document.querySelector('[data-problem-code="permission_denied"]')).toHaveTextContent('workflow manage'));
  });

  it('is restricted, with no entry under Admin, without workflow.manage', async () => {
    const sent = server();
    await renderScreen(['audit.read', 'members.manage']);
    expect(screen.getByRole('alert')).toHaveTextContent('workflow manage');
    expect(screen.queryByLabelText('Escalate after')).toBeNull();
    expect(sent.filter((s) => s.path === TENANT_PATH)).toEqual([]);
    expect(childDestinations('admin', ['audit.read', 'members.manage']).map((d) => d.id)).not.toContain('admin-workflow');
    expect(childDestinations('admin', ['workflow.manage']).map((d) => d.id)).toContain('admin-workflow');
  });
});
