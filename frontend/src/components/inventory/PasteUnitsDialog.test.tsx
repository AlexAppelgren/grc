import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { PasteUnitsDialog, parsePastedUnits } from './PasteUnitsDialog';

// "Paste units" (REG-08, REG-01, AC-REG1): the dry run stores nothing and
// names each refused line and why; creating sends only the ready lines, and
// every decision the paste carries is confirmed in one dialog and set in one
// call. Without applicability.approve the decisions are left out.

const words = { applies: 'applies', doesNotApply: 'does not apply' };
const entity = { id: 'e-bank', name: 'Example Bank AB' };

interface PastedLine {
  reference: string;
  title: string;
}

/** The server's dry run and commit: refuses SEC-012 as already listed, creates the rest. */
function paste(sent: Sent): Answer {
  const body = sent.body as { lines: PastedLine[]; dryRun: boolean };
  return {
    status: 200,
    data: {
      dryRun: body.dryRun,
      created: body.dryRun ? 0 : body.lines.length,
      rows: body.lines.map((line, index) => {
        const exists = line.reference === 'SEC-012';
        return {
          line: index + 1,
          reference: line.reference.trim(),
          title: line.title.trim(),
          outcome: exists ? 'refused' : body.dryRun ? 'will_create' : 'created',
          problem: exists ? 'reference_exists' : null,
          unitId: body.dryRun || exists ? null : `u-${line.reference}`,
        };
      }),
    },
  };
}

function serve(decide: () => Answer = () => ({ status: 200, data: { items: [] } }), dryRun: (sent: Sent) => Answer = paste): Sent[] {
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/applicability') return decide();
    if (sent.path === '/api/v1/obligations/ob-std/units/paste') return (sent.body as { dryRun: boolean }).dryRun ? dryRun(sent) : paste(sent);
    return { status: 404, data: { code: 'not_found', detail: '' } };
  });
}

function renderDialog(canDecide: boolean) {
  const onCreated = vi.fn();
  const onOpenChange = vi.fn();
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  render(
    <Wrapper>
      <LocaleProvider locale="en">
        <PasteUnitsDialog obligationId="ob-std" entity={entity} canDecide={canDecide} open onOpenChange={onOpenChange} onCreated={onCreated} />
      </LocaleProvider>
    </Wrapper>,
  );
  return { onCreated, onOpenChange };
}

const pasted = ['SEC-001\tPolicy is approved by the board\tapplies\tBoard owns it', 'SEC-003\tClean desk rule in the branches\tdoes not apply\tWe have no branches', 'SEC-005\tLaptops are encrypted', 'SEC-012\tAccess is reviewed', 'SEC-023\tSuppliers sign an annex\tmaybe\tNot sure'].join('\n');

async function checkLines(text: string) {
  fireEvent.change(screen.getByLabelText('One unit per line'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Check the lines' }));
  await screen.findByRole('heading', { name: 'Check before you create' });
}

const calls = (sent: Sent[], path: string) => sent.filter((call) => call.path === path);

describe('parsePastedUnits', () => {
  it('reads reference, title, decision and reason, skipping blank lines', () => {
    const lines = parsePastedUnits('A.1\tOur policy\tApplies\tCertified\n\n  \nA.2\tOur roles\n', words, true);
    expect(lines).toEqual([
      { reference: 'A.1', title: 'Our policy', decision: 'applies', reason: 'Certified', word: 'Applies', problem: null },
      { reference: 'A.2', title: 'Our roles', decision: null, reason: '', word: '', problem: null },
    ]);
  });

  it('refuses an unknown decision word and a decision without a reason', () => {
    const [unknown, bare] = parsePastedUnits('A.1\tOur policy\tmaybe\tSure\nA.2\tOur roles\tdoes not apply', words, true);
    expect(unknown).toMatchObject({ decision: null, word: 'maybe', problem: 'decision' });
    expect(bare).toMatchObject({ decision: 'not_applicable', problem: 'reason' });
  });

  it('ignores the decision columns when the person may not decide', () => {
    expect(parsePastedUnits('A.1\tOur policy\tmaybe', words, false)).toEqual([{ reference: 'A.1', title: 'Our policy', decision: null, reason: '', word: '', problem: null }]);
  });
});

describe('PasteUnitsDialog', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('asks for the bank own list and offers no field for the standard text', () => {
    serve();
    renderDialog(true);
    expect(screen.getByRole('dialog', { name: 'Paste units for Example Bank AB' })).toBeInTheDocument();
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(screen.getByText(/Your reference, a tab, your title/)).toBeInTheDocument();
  });

  it('shows the dry run with every refused line and why, storing nothing', async () => {
    const sent = serve();
    renderDialog(true);
    await checkLines(pasted);

    const dryRuns = calls(sent, '/api/v1/obligations/ob-std/units/paste');
    expect(dryRuns).toHaveLength(1);
    expect(dryRuns[0]?.body).toEqual({
      orgUnitId: 'e-bank',
      dryRun: true,
      lines: [
        { reference: 'SEC-001', title: 'Policy is approved by the board' },
        { reference: 'SEC-003', title: 'Clean desk rule in the branches' },
        { reference: 'SEC-005', title: 'Laptops are encrypted' },
        { reference: 'SEC-012', title: 'Access is reviewed' },
        { reference: 'SEC-023', title: 'Suppliers sign an annex' },
      ],
    });
    expect(screen.getByText('Nothing is stored yet.')).toBeInTheDocument();

    const ready = document.querySelector<HTMLElement>('[data-paste-ready]');
    if (ready === null) throw new Error('no ready table');
    expect(screen.getByRole('heading', { name: '3 units to create' })).toBeInTheDocument();
    expect(within(ready).getByText('SEC-001')).toBeInTheDocument();
    expect(within(ready).getByText('Applies')).toBeInTheDocument();
    expect(within(ready).getByText('Does not apply')).toBeInTheDocument();
    expect(within(ready).getByText('None')).toBeInTheDocument();

    const refused = document.querySelector<HTMLElement>('[data-paste-refused]');
    if (refused === null) throw new Error('no refused table');
    expect(screen.getByRole('heading', { name: '2 lines refused and left out' })).toBeInTheDocument();
    expect(within(refused).getByText('Example Bank AB already has a unit with this reference.')).toBeInTheDocument();
    expect(within(refused).getByText('"maybe" is not a decision. Use "applies" or "does not apply", or leave it out.')).toBeInTheDocument();
    expect(calls(sent, '/api/v1/applicability')).toHaveLength(0);
  });

  it('creates the ready lines without a confirmation when the paste carries no decision', async () => {
    const sent = serve();
    const { onCreated } = renderDialog(true);
    await checkLines('SEC-005\tLaptops are encrypted\nSEC-012\tAccess is reviewed');
    fireEvent.click(screen.getByRole('button', { name: 'Create 1 unit' }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(1));
    const commit = calls(sent, '/api/v1/obligations/ob-std/units/paste')[1];
    expect(commit?.body).toEqual({ orgUnitId: 'e-bank', dryRun: false, lines: [{ reference: 'SEC-005', title: 'Laptops are encrypted' }] });
    expect(calls(sent, '/api/v1/applicability')).toHaveLength(0);
  });

  it('lists every decision in one confirmation and sets them in one call', async () => {
    const sent = serve();
    const { onCreated } = renderDialog(true);
    await checkLines(pasted);
    fireEvent.click(screen.getByRole('button', { name: 'Create 3 units' }));

    const confirm = await screen.findByRole('dialog', { name: 'Set 2 decisions for Example Bank AB?' });
    expect(within(confirm).getByText('Board owns it')).toBeInTheDocument();
    expect(within(confirm).getByText('We have no branches')).toBeInTheDocument();
    expect(calls(sent, '/api/v1/obligations/ob-std/units/paste')).toHaveLength(1);

    // Cancel stores nothing and goes back to the dry run.
    fireEvent.click(within(confirm).getByRole('button', { name: 'Cancel' }));
    await screen.findByRole('heading', { name: 'Check before you create' });
    expect(calls(sent, '/api/v1/obligations/ob-std/units/paste')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Create 3 units' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Set 2 decisions' }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(3));
    expect(onCreated).toHaveBeenCalledTimes(1);
    // The units and their decisions go together in the paste's one commit, all or none.
    expect(calls(sent, '/api/v1/obligations/ob-std/units/paste')[1]?.body).toEqual({
      orgUnitId: 'e-bank',
      dryRun: false,
      lines: [
        { reference: 'SEC-001', title: 'Policy is approved by the board', applicability: 'applies', reason: 'Board owns it' },
        { reference: 'SEC-003', title: 'Clean desk rule in the branches', applicability: 'not_applicable', reason: 'We have no branches' },
        { reference: 'SEC-005', title: 'Laptops are encrypted' },
      ],
    });
    expect(calls(sent, '/api/v1/applicability')).toHaveLength(0);
  });

  it('leaves the decisions out for a person without applicability approve, and says so', async () => {
    const sent = serve();
    const { onCreated } = renderDialog(false);
    await checkLines(pasted);

    expect(screen.getByText('The decisions are left out: setting applicability needs applicability approve.')).toBeInTheDocument();
    expect(screen.queryByText('Applies')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Create 4 units' }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(4));
    expect(calls(sent, '/api/v1/applicability')).toHaveLength(0);
  });

  it('keeps the confirmation open when the commit is refused, having stored nothing', async () => {
    let failing = true;
    const sent = installAdapter((call) => {
      const body = call.body as { dryRun: boolean };
      if (call.path !== '/api/v1/obligations/ob-std/units/paste') return { status: 404, data: { code: 'not_found', detail: '' } };
      if (!body.dryRun && failing) return { status: 422, data: { code: 'validation_error', detail: 'A reason is too long.' } };
      return paste(call);
    });
    const { onCreated } = renderDialog(true);
    await checkLines(pasted);
    fireEvent.click(screen.getByRole('button', { name: 'Create 3 units' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Set 2 decisions' }));

    expect(await screen.findByText('A reason is too long.')).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();

    failing = false;
    fireEvent.click(screen.getByRole('button', { name: 'Set 2 decisions' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(3));
    expect(calls(sent, '/api/v1/obligations/ob-std/units/paste')).toHaveLength(3);
    expect(calls(sent, '/api/v1/applicability')).toHaveLength(0);
  });

  it('renders a refusal of the whole paste where it happened', async () => {
    serve(undefined, () => ({ status: 422, data: { code: 'scope_not_applicable', detail: 'Units are listed only for a legal entity that follows the standard.' } }));
    renderDialog(true);
    fireEvent.change(screen.getByLabelText('One unit per line'), { target: { value: 'A.1\tOur policy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check the lines' }));

    expect(await screen.findByText('Example Bank AB does not follow this standard, so it cannot have units. Set "Applies" for it on the obligation first.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Check before you create' })).not.toBeInTheDocument();
  });
});
