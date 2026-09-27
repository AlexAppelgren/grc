import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { RegisterEntityStatus, RegisterUnit } from '@/features/register/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { ObligationUnitsPanel } from './ObligationUnitsPanel';

// "Units" on a standard's conformance obligation (REG-08): listed per legal
// entity, the picker offering only the entities that follow the standard;
// add, rename and remove for a holder of register.edit, rename and remove
// giving way to a fixed line once a unit has history.

const READER = ['register.read'];
const OFFICER = ['register.read', 'register.edit', 'applicability.approve'];

const notAssessed = { key: 'not_assessed', kind: 'not_assessed', label: 'Not assessed' };
const person = { id: 'p-sara', name: 'Sara Lindqvist' };

function entityRow(orgUnitId: string, orgUnitName: string, applicability: RegisterEntityStatus['applicability']): RegisterEntityStatus {
  return {
    orgUnitId,
    orgUnitName,
    applicability,
    applicabilityReason: null,
    applicabilityDecidedAt: null,
    applicabilityDecidedBy: null,
    complianceStatus: notAssessed,
    statusNote: null,
    riskRating: null,
  } as unknown as RegisterEntityStatus;
}

const entities = [entityRow('e-bank', 'Example Bank AB', 'applies'), entityRow('e-fonder', 'Example Fonder AB', 'applies'), entityRow('e-liv', 'Example Liv Försäkring AB', 'not_applicable')];

const decided: RegisterUnit = {
  id: 'u-012',
  obligationId: 'ob-std',
  orgUnitId: 'e-bank',
  reference: 'SEC-012',
  title: 'Access to the payments system is reviewed every quarter',
  applicability: 'applies',
  applicabilityReason: 'Payments staff change often.',
  applicabilityDecidedAt: '2026-09-18T12:02:00Z',
  applicabilityDecidedBy: person,
  complianceStatus: { key: 'partly', kind: 'partially_compliant', label: 'Partly compliant' },
  hasHistory: true,
  version: 3,
};
const fresh: RegisterUnit = {
  ...decided,
  id: 'u-044',
  reference: 'SEC-044',
  title: 'Backups are restored in a test once a year',
  applicability: 'under_assessment',
  applicabilityReason: null,
  applicabilityDecidedAt: null,
  applicabilityDecidedBy: null,
  complianceStatus: notAssessed,
  hasHistory: false,
  version: 1,
};

function meWith(permissions: string[]) {
  return { user: { id: 'me', name: 'Me', locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, permissions, enrolmentPending: false };
}

function serve(permissions: string[], rows: RegisterEntityStatus[], units: (sent: Sent) => Answer, write: (sent: Sent) => Answer = () => ({ status: 200, data: {} })): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/me') return { status: 200, data: meWith(permissions) };
    if (sent.path === '/api/v1/obligations/ob-std/register') return { status: 200, data: { entities: rows } };
    if (sent.method === 'get' && sent.path === '/api/v1/obligations/ob-std/units') return units(sent);
    return write(sent);
  });
}

const page = (items: RegisterUnit[]): Answer => ({ status: 200, data: { items, total: items.length } });

function renderPanel(permissions: string[]) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <ObligationUnitsPanel obligationId="ob-std" />
        </PermissionsProvider>
      </LocaleProvider>
    </Wrapper>,
  );
}

function row(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-unit-id="${id}"]`);
  if (found === null) throw new Error(`no row ${id}`);
  return found;
}

describe('ObligationUnitsPanel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('offers only the legal entities that follow the standard and lists the chosen one units', async () => {
    const sent = serve(OFFICER, entities, (call) => page((call.params as { entity: string }).entity === 'e-bank' ? [decided, fresh] : []));
    renderPanel(OFFICER);

    const picker = await screen.findByLabelText('Legal entity');
    expect(within(picker).getAllByRole('option').map((option) => option.textContent)).toEqual(['Example Bank AB', 'Example Fonder AB']);
    expect(screen.getByText('Only legal entities where this standard applies are listed. Not listed: Example Liv Försäkring AB.')).toBeInTheDocument();

    await screen.findByText('2 units');
    expect(within(row('u-012')).getByText('SEC-012')).toBeInTheDocument();
    expect(within(row('u-012')).getByText('Applies')).toBeInTheDocument();
    expect(within(row('u-012')).getByText('Partly compliant')).toBeInTheDocument();
    expect(within(row('u-012')).getByText('Set by Sara Lindqvist')).toBeInTheDocument();
    expect(within(row('u-044')).getByText('No decision yet')).toBeInTheDocument();
    expect(within(row('u-044')).getAllByText('Not assessed')).toHaveLength(1);

    fireEvent.change(picker, { target: { value: 'e-fonder' } });
    expect(await screen.findByText('No units for Example Fonder AB')).toBeInTheDocument();
    const lists = sent.filter((call) => call.path === '/api/v1/obligations/ob-std/units').map((call) => (call.params as { entity: string }).entity);
    expect(lists).toEqual(['e-bank', 'e-fonder']);
  });

  it('shows the chosen entity Statement of Applicability on its own tab', async () => {
    const statement = { obligationId: 'ob-std', conformance: entities[0], units: [{ ...decided, history: [] }], total: 1 };
    const sent = serve(OFFICER, entities, () => page([decided]), (call) =>
      call.path === '/api/v1/obligations/ob-std/statement-of-applicability' ? { status: 200, data: statement } : { status: 200, data: {} },
    );
    renderPanel(OFFICER);
    await screen.findByText('1 unit');

    fireEvent.click(screen.getByRole('tab', { name: 'Statement of Applicability' }));
    expect(await screen.findByRole('heading', { name: 'Conformance for Example Bank AB' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Paste units' })).not.toBeInTheDocument();
    const reads = sent.filter((call) => call.path === '/api/v1/obligations/ob-std/statement-of-applicability');
    expect(reads.map((call) => (call.params as { entity: string }).entity)).toEqual(['e-bank']);
  });

  it('fixes the reference and title of a unit with history and offers rename and remove before then', async () => {
    serve(OFFICER, entities, () => page([decided, fresh]));
    renderPanel(OFFICER);
    await screen.findByText('2 units');

    expect(within(row('u-012')).getByText('Reference and title are fixed: this unit has history.')).toBeInTheDocument();
    expect(within(row('u-012')).queryByRole('button', { name: 'Rename' })).not.toBeInTheDocument();
    expect(within(row('u-012')).queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
    expect(within(row('u-044')).getByRole('button', { name: 'Rename' })).toBeInTheDocument();
    expect(within(row('u-044')).getByRole('button', { name: 'Remove' })).toBeInTheDocument();
  });

  it('shows a reader the units and no action', async () => {
    serve(READER, entities, () => page([decided, fresh]));
    renderPanel(READER);
    await screen.findByText('2 units');

    expect(screen.queryByRole('button', { name: 'Add a unit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Paste units' })).not.toBeInTheDocument();
    expect(within(row('u-044')).queryByRole('button', { name: 'Rename' })).not.toBeInTheDocument();
  });

  it('says so when no legal entity follows the standard', async () => {
    const sent = serve(OFFICER, [entities[2] as RegisterEntityStatus], () => page([]));
    renderPanel(OFFICER);

    expect(await screen.findByRole('heading', { name: 'No legal entity follows this standard' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Legal entity')).not.toBeInTheDocument();
    expect(sent.some((call) => call.path === '/api/v1/obligations/ob-std/units')).toBe(false);
  });

  it('adds a unit in the bank own words and renders a duplicate where it happened', async () => {
    let duplicate = true;
    const sent = serve(OFFICER, entities, () => page([]), () =>
      duplicate ? { status: 409, data: { code: 'duplicate_key', detail: 'This entity already lists SEC-012.' } } : { status: 201, data: fresh },
    );
    renderPanel(OFFICER);
    fireEvent.click(await screen.findByRole('button', { name: 'Add a unit' }));

    const dialog = await screen.findByRole('dialog', { name: 'Add a unit for Example Bank AB' });
    expect(within(dialog).getAllByRole('textbox')).toHaveLength(2);
    expect(within(dialog).getByText("In your own words, as your own list has it. Do not copy the standard's text.")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText('Your reference'), { target: { value: ' SEC-012 ' } });
    fireEvent.change(within(dialog).getByLabelText('Your title'), { target: { value: 'Backups are restored' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add unit' }));

    expect(await within(dialog).findByText('Example Bank AB already has a unit with this reference.')).toBeInTheDocument();
    const create = sent.find((call) => call.method === 'post');
    expect(create?.path).toBe('/api/v1/obligations/ob-std/units');
    expect(create?.body).toEqual({ orgUnitId: 'e-bank', reference: 'SEC-012', title: 'Backups are restored' });

    duplicate = false;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add unit' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('renames a unit with its version and offers a reload after a stale write', async () => {
    const sent = serve(OFFICER, entities, () => page([fresh]), () => ({ status: 409, data: { code: 'stale_write', detail: 'Changed.' } }));
    renderPanel(OFFICER);
    await screen.findByText('1 unit');
    fireEvent.click(within(row('u-044')).getByRole('button', { name: 'Rename' }));

    const dialog = await screen.findByRole('dialog', { name: 'Rename SEC-044' });
    expect(within(dialog).getByLabelText('Your reference')).toHaveValue('SEC-044');
    fireEvent.change(within(dialog).getByLabelText('Your title'), { target: { value: 'Backups are restored twice a year' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(await within(dialog).findByText('Someone changed this unit while you were editing. Reload to see their version, then make your change again.')).toBeInTheDocument();
    const patch = sent.find((call) => call.method === 'patch');
    expect(patch?.path).toBe('/api/v1/units/u-044');
    expect(patch?.body).toEqual({ reference: 'SEC-044', title: 'Backups are restored twice a year' });

    const listsBefore = sent.filter((call) => call.path === '/api/v1/obligations/ob-std/units').length;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reload' }));
    await waitFor(() => expect(sent.filter((call) => call.path === '/api/v1/obligations/ob-std/units').length).toBeGreaterThan(listsBefore));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('removes a unit with no history after a confirmation', async () => {
    const sent = serve(OFFICER, entities, () => page([fresh]), () => ({ status: 204 }));
    renderPanel(OFFICER);
    await screen.findByText('1 unit');
    fireEvent.click(within(row('u-044')).getByRole('button', { name: 'Remove' }));

    const dialog = await screen.findByRole('dialog', { name: 'Remove SEC-044?' });
    expect(within(dialog).getByText('"Backups are restored in a test once a year" leaves the list. It has no decisions, so nothing else changes.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const remove = sent.find((call) => call.method === 'delete');
    expect(remove?.path).toBe('/api/v1/units/u-044');
  });

  it('says how many units a paste created', async () => {
    serve(OFFICER, entities, () => page([]), (call) => {
      const body = call.body as { lines: { reference: string; title: string }[]; dryRun: boolean };
      return {
        status: 200,
        data: {
          dryRun: body.dryRun,
          created: body.dryRun ? 0 : body.lines.length,
          rows: body.lines.map((line, index) => ({ line: index + 1, ...line, outcome: body.dryRun ? 'will_create' : 'created', problem: null, unitId: body.dryRun ? null : `u-${index}` })),
        },
      };
    });
    renderPanel(OFFICER);
    fireEvent.click(await screen.findByRole('button', { name: 'Paste units' }));
    fireEvent.change(await screen.findByLabelText('One unit per line'), { target: { value: 'A.1\tOur policy\nA.2\tOur roles' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check the lines' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Create 2 units' }));

    expect(await screen.findByText('2 units created.')).toBeInTheDocument();
  });
});
