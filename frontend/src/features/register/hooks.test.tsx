import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, queryWrapper, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { COLLAB_PAGE, useComments } from '@/features/collab/hooks';
import { PARTICIPANTS_PAGE } from '@/features/participants/api';
import { useObligationParticipants } from '@/features/participants/hooks';
import { RECORD_REPORTS_PAGE, useRecordProblemReports } from '@/features/problem-reports/hooks';
import { CHANGE_PAGE, useObligationChanges } from '@/features/watch/hooks';

import * as hooks from './hooks';
import { withPanels } from './testing';

// Every register read and write goes through these hooks. A write refreshes
// the register reads; a stale write is neither retried nor merged, and Reload
// fetches the version someone else saved.

describe('register hooks', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('reads every register list and record, and the entry can wait', async () => {
    const sent = installAdapter((s) => ({ status: 200, data: s.path.endsWith('/register') ? withPanels({ path: s.path }) : { path: s.path } }));
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
        hooks.useInternalItems('reconc', true),
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
        '/api/v1/obligations/ob1/internal-links',
        '/api/v1/obligations/ob1/units',
        '/api/v1/obligations/ob1/statement-of-applicability',
        '/api/v1/obligations/ob1/duties',
        '/api/v1/internal-items',
      ]),
    );
    const waiting = renderHook(() => hooks.useRegisterEntry('ob2', false), { wrapper });
    expect(waiting.result.current.fetchStatus).toBe('idle');
    expect(renderHook(() => hooks.useInternalItems('x', false), { wrapper }).result.current.fetchStatus).toBe('idle');
    expect(hooks.registerKeys.units('ob1', undefined, {})).toEqual(['register', 'obligation', 'ob1', 'units', null, {}]);
  });

  it('writes through every mutation and refreshes the register reads afterwards', async () => {
    const sent = installAdapter((s) => ({ status: s.method === 'delete' ? 204 : 200, data: withPanels({ version: 1 }) }));
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
      s.method === 'patch' ? { status: 409, data: { status: 409, code: 'stale_write', title: 'Changed', detail: '' } } : { status: 200, data: withPanels({ version: saved }) },
    );
    const { wrapper } = queryWrapper();
    const view = renderHook(() => ({ entry: hooks.useRegisterEntry('ob1'), update: hooks.useUpdateRegister('ob1'), reload: hooks.useReloadRegister() }), { wrapper });
    await waitFor(() => expect(view.result.current.entry.data?.version).toBe(4));

    saved = 5;
    await act(async () => {
      await view.result.current.update.mutateAsync({ body: { statusNote: 'Mine' }, version: 4 }).catch(() => undefined);
    });
    await waitFor(() => expect(hooks.isStaleWrite(view.result.current.update.error)).toBe(true));
    expect(sent.filter((s) => s.method === 'patch')).toHaveLength(1);
    // Nothing merged: the read still holds what was loaded until Reload.
    expect(view.result.current.entry.data?.version).toBe(4);

    await act(async () => {
      await view.result.current.reload();
    });
    await waitFor(() => expect(view.result.current.entry.data?.version).toBe(5));
    expect(hooks.isStaleWrite(new Error('offline'))).toBe(false);
  });

  describe('the obligation page\'s one read', () => {
    const page = <T,>(items: T[]) => ({ items, total: items.length });
    const PARTS = {
      spannedEntities: [{ orgUnitId: 'e1', orgUnitName: 'Example Bank AB' }],
      gaps: page([{ id: 'g1' }]),
      assessments: page([{ id: 'a1' }]),
      internalLinks: page([{ id: 'l1' }]),
      units: { orgUnitId: 'e1', units: page([{ id: 'u1' }]) },
      participants: page([{ id: 'p1' }]),
      problemReports: page([{ id: 'r1' }]),
      changes: { ...page([{ id: 'c1' }]), openCount: 1 },
      comments: page([{ id: 'm1' }]),
    };

    /** A client that keeps data fresh for 30 seconds, as the app's own does (app/providers.tsx). */
    function freshWrapper() {
      const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: false } } });
      return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children);
    }

    function usePanelReads(obligationId: string) {
      return [
        hooks.useSpannedEntities(obligationId),
        hooks.useObligationGaps(obligationId, hooks.OBLIGATION_GAPS_PAGE),
        hooks.useAssessments(obligationId, hooks.FIRST_ASSESSMENTS_PAGE),
        hooks.useInternalLinks(obligationId),
        hooks.useUnits(obligationId, 'e1', hooks.FIRST_UNITS_PAGE),
        useObligationParticipants(obligationId),
        useRecordProblemReports('obligation', obligationId, true),
        useObligationChanges(obligationId),
        useComments({ subjectType: 'obligation', subjectId: obligationId }),
      ] as const;
    }

    it('leaves every panel\'s first page where the panel reads it, so a panel mounted after it asks nothing', async () => {
      const sent = installAdapter(() => ({ status: 200, data: withPanels({ version: 3 }, PARTS as never) }));
      const wrapper = freshWrapper();
      const entry = renderHook(() => hooks.useRegisterEntry('ob1'), { wrapper });
      await waitFor(() => expect(entry.result.current.isSuccess).toBe(true));

      const panels = renderHook(() => usePanelReads('ob1'), { wrapper });
      const [span, gaps, assessments, links, units, participants, reports, changes, comments] = panels.result.current;
      expect(span.data).toEqual(PARTS.spannedEntities);
      expect(gaps.data).toEqual(PARTS.gaps);
      expect(assessments.data).toEqual(PARTS.assessments);
      expect(links.data).toEqual(PARTS.internalLinks);
      expect(units.data).toEqual(PARTS.units.units);
      expect(participants.data).toEqual(PARTS.participants);
      expect(reports.data).toEqual(PARTS.problemReports);
      expect(changes.data).toEqual(PARTS.changes);
      expect(comments.data?.pages).toEqual([PARTS.comments]);
      expect(sent.map((call) => call.path)).toEqual(['/api/v1/obligations/ob1/register']);
    });

    it('leaves a part the reader may not read to its own route, and never replaces what a panel read itself', async () => {
      const sent = installAdapter((call) =>
        call.path.endsWith('/register')
          ? { status: 200, data: withPanels({ version: 3 }, { ...PARTS, problemReports: null, changes: null, comments: null } as never) }
          : { status: 200, data: page([{ id: 'own' }]) },
      );
      const wrapper = freshWrapper();
      // The links panel read its own page before the entry answered.
      const links = renderHook(() => hooks.useInternalLinks('ob1'), { wrapper });
      await waitFor(() => expect(links.result.current.isSuccess).toBe(true));
      const entry = renderHook(() => hooks.useRegisterEntry('ob1'), { wrapper });
      await waitFor(() => expect(entry.result.current.isSuccess).toBe(true));
      expect(links.result.current.data).toEqual(page([{ id: 'own' }]));

      renderHook(() => [useRecordProblemReports('obligation', 'ob1', true), useObligationChanges('ob1'), useComments({ subjectType: 'obligation', subjectId: 'ob1' })], { wrapper });
      await waitFor(() => expect(sent.map((call) => call.path)).toEqual(expect.arrayContaining(['/api/v1/problem-reports', '/api/v1/obligations/ob1/changes', '/api/v1/comments'])));
    });

    it('carries the pages the panels ask their own routes for, as the server fills them', () => {
      // backend/apps/register/panels.py: FIRST_PAGE 20 and WHOLE_LIST 100.
      expect([hooks.PANEL_PAGE, CHANGE_PAGE, COLLAB_PAGE, RECORD_REPORTS_PAGE]).toEqual([20, 20, 20, 20]);
      expect([hooks.PANEL_WHOLE_LIST, PARTICIPANTS_PAGE]).toEqual([100, 100]);
      expect(hooks.OBLIGATION_GAPS_PAGE).toEqual({ limit: 100 });
      expect(hooks.FIRST_ASSESSMENTS_PAGE).toEqual({ limit: 20, offset: 0 });
      expect(hooks.FIRST_UNITS_PAGE).toEqual({ limit: 100, offset: 0 });
    });
  });
});
