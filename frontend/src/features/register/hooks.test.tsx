import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as hooks from './hooks';

// Every register read and write goes through these hooks. A write refreshes
// the register reads; a stale write is neither retried nor merged, and Reload
// fetches the version someone else saved.

describe('register hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads every register list and record, and the entry can wait', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: { path: s.path } }));
    const { wrapper } = queryWrapper();
    const reads = renderHook(
      () => [
        hooks.useRegisterEntry('ob1'),
        hooks.useObligationGaps('ob1'),
        hooks.useGaps({ status: 'open' }),
        hooks.useAssessments('ob1'),
        hooks.useInterpretation('ob1'),
        hooks.useInternalLinks('ob1'),
        hooks.useUnits('ob1', 'e1'),
        hooks.useStatementOfApplicability('ob1', 'e1'),
        hooks.useDuties('ob1'),
      ],
      { wrapper },
    );
    await waitFor(() => expect(reads.result.current.every((query) => query.isSuccess)).toBe(true));
    expect(new Set(sent.map((s) => s.path))).toEqual(
      new Set([
        '/api/v1/obligations/ob1/register',
        '/api/v1/obligations/ob1/gaps',
        '/api/v1/gaps',
        '/api/v1/obligations/ob1/assessments',
        '/api/v1/obligations/ob1/interpretation',
        '/api/v1/obligations/ob1/internal-links',
        '/api/v1/obligations/ob1/units',
        '/api/v1/obligations/ob1/statement-of-applicability',
        '/api/v1/obligations/ob1/duties',
      ]),
    );
    const waiting = renderHook(() => hooks.useRegisterEntry('ob2', false), { wrapper });
    expect(waiting.result.current.fetchStatus).toBe('idle');
    expect(hooks.registerKeys.units('ob1', undefined, {})).toEqual(['register', 'obligation', 'ob1', 'units', null, {}]);
  });

  it('writes through every mutation and refreshes the register reads afterwards', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: { version: 1 } }));
    const { wrapper } = queryWrapper();
    const entry = renderHook(() => hooks.useRegisterEntry('ob1'), { wrapper });
    await waitFor(() => expect(entry.result.current.isSuccess).toBe(true));
    const writes = renderHook(
      () => ({
        updateRegister: hooks.useUpdateRegister('ob1'),
        updateEntity: hooks.useUpdateRegisterEntity('ob1'),
        setApplicability: hooks.useSetApplicability('ob1'),
        setMany: hooks.useSetApplicabilityMany(),
        createGap: hooks.useCreateGap('ob1'),
        updateGap: hooks.useUpdateGap(),
        requestRisk: hooks.useRequestRiskAcceptance(),
        approveRisk: hooks.useApproveRiskAcceptance(),
        reopenGap: hooks.useReopenGap(),
        saveInterpretation: hooks.useSaveInterpretation('ob1'),
        addLink: hooks.useAddInternalLink('ob1'),
        removeLink: hooks.useRemoveInternalLink(),
        createUnit: hooks.useCreateUnit('ob1'),
        updateUnit: hooks.useUpdateUnit(),
        removeUnit: hooks.useRemoveUnit(),
        pasteUnits: hooks.usePasteUnits('ob1'),
        completeDuty: hooks.useCompleteDutyOccurrence(),
      }),
      { wrapper },
    );
    const w = writes.result.current;
    await act(async () => {
      await w.updateRegister.mutateAsync({ body: { statusNote: 'Daily' }, version: 1 });
      await w.updateEntity.mutateAsync({ orgUnitId: 'e1', body: { complianceStatus: 'gap' }, version: 0 });
      await w.setApplicability.mutateAsync({ body: { applicability: 'applies', reason: 'Licensed' }, version: 2 });
      await w.setMany.mutateAsync({ rows: [{ obligationId: 'ob1', applicability: 'applies', reason: 'Licensed' }] });
      await w.createGap.mutateAsync({ severity: 'high', source: 'assessment', title: 'No yearly review' });
      await w.updateGap.mutateAsync({ gapId: 'g1', body: { status: 'remediating' }, version: 1 });
      await w.requestRisk.mutateAsync({ gapId: 'g1', body: { reason: 'cost_exceeds_benefit' } });
      await w.approveRisk.mutateAsync('g1');
      await w.reopenGap.mutateAsync('g1');
      await w.saveInterpretation.mutateAsync({ body: { text: 'Research covers analysts.' }, version: 3 });
      await w.addLink.mutateAsync({ kind: 'policy', label: 'Client asset policy' });
      await w.removeLink.mutateAsync('l1');
      await w.createUnit.mutateAsync({ orgUnitId: 'e1', reference: 'A.5.1', title: 'Policies' });
      await w.updateUnit.mutateAsync({ unitId: 'u1', body: { title: 'Policies' }, version: 1 });
      await w.removeUnit.mutateAsync({ unitId: 'u1', version: 2 });
      await w.pasteUnits.mutateAsync({ orgUnitId: 'e1', lines: [{ reference: 'A.5.1', title: 'Policies' }], dryRun: true });
      await w.completeDuty.mutateAsync({ occurrenceId: 'o1', body: {} });
    });
    const written = sent.filter((s) => s.method !== 'get');
    expect(written).toHaveLength(17);
    // The entry was read once, then again after the writes invalidated it.
    await waitFor(() => expect(sent.filter((s) => s.method === 'get').length).toBeGreaterThan(1));
  });

  it('keeps a stale write unsent a second time and reloads the saved version on request', async () => {
    let saved = 4;
    const sent = installAdapter((s) =>
      s.method === 'patch' ? { status: 409, data: { status: 409, code: 'stale_write', title: 'Changed', detail: '' } } : { status: 200, data: { version: saved } },
    );
    const { wrapper } = queryWrapper();
    const view = renderHook(() => ({ entry: hooks.useRegisterEntry('ob1'), update: hooks.useUpdateRegister('ob1'), reload: hooks.useReloadRegister() }), { wrapper });
    await waitFor(() => expect(view.result.current.entry.data).toEqual({ version: 4 }));

    saved = 5;
    await act(async () => {
      await view.result.current.update.mutateAsync({ body: { statusNote: 'Mine' }, version: 4 }).catch(() => undefined);
    });
    await waitFor(() => expect(hooks.isStaleWrite(view.result.current.update.error)).toBe(true));
    expect(sent.filter((s) => s.method === 'patch')).toHaveLength(1);
    // Nothing merged: the read still holds what was loaded until Reload.
    expect(view.result.current.entry.data).toEqual({ version: 4 });

    await act(async () => {
      await view.result.current.reload();
    });
    await waitFor(() => expect(view.result.current.entry.data).toEqual({ version: 5 }));
    expect(hooks.isStaleWrite(new Error('offline'))).toBe(false);
  });
});
