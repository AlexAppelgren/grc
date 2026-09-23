'use client';

import { useMutation, useQuery, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';

import * as library from './api';
import type {
  Instrument,
  InstrumentDetail,
  InstrumentQuery,
  Obligation,
  ObligationDetail,
  ObligationQuery,
  Page,
  ProblemReportBody,
  ProblemReportCreated,
  ProvisionNode,
  VersionDiff,
} from './types';

// Query keys for the inventory and the obligation card (playbook 6.1). The
// filters and the date are part of the key, so changing "as of" or asking to
// see outside the footprint re-reads rather than reuses: the version in force
// on a date is a different answer, not a filtered one.

export const libraryKeys = {
  obligations: (query: ObligationQuery, limit: number) => ['library', 'obligations', { ...query, limit }] as const,
  obligation: (obligationId: string, asOf: string) => ['library', 'obligation', obligationId, asOf] as const,
  obligationDiff: (obligationId: string, lang: string) => ['library', 'obligation', obligationId, 'diff', lang] as const,
  instruments: (query: InstrumentQuery, limit: number) => ['library', 'instruments', { ...query, limit }] as const,
  instrument: (instrumentId: string) => ['library', 'instrument', instrumentId] as const,
  provisions: (instrumentId: string, asOf: string) => ['library', 'instrument', instrumentId, 'provisions', asOf] as const,
  provisionDiff: (provisionId: string, lang: string) => ['library', 'provision', provisionId, 'diff', lang] as const,
};

/** Playbook 10: the list default. The head states the total, so a longer library is visibly longer than the page. */
export const OBLIGATION_PAGE = 20;

export function useObligations(query: ObligationQuery): UseQueryResult<Page<Obligation>> {
  return useQuery({
    queryKey: libraryKeys.obligations(query, OBLIGATION_PAGE),
    queryFn: () => library.listObligations({ ...query, limit: OBLIGATION_PAGE, offset: 0 }),
  });
}

/**
 * One obligation as of a date. The date is part of the key, so "as of" is a
 * different answer rather than a filtered one, and an empty date means today
 * in the bank's own time zone, which the server decides.
 */
export function useObligation(obligationId: string, asOf = ''): UseQueryResult<ObligationDetail> {
  return useQuery({
    queryKey: libraryKeys.obligation(obligationId, asOf),
    queryFn: () => library.getObligation(obligationId, asOf),
  });
}

/** "Show what changed", read only once the reader asks for it. */
export function useObligationDiff(obligationId: string, lang: string, enabled: boolean): UseQueryResult<VersionDiff> {
  return useQuery({
    queryKey: libraryKeys.obligationDiff(obligationId, lang),
    queryFn: () => library.getObligationDiff(obligationId, lang),
    enabled,
  });
}

/**
 * Filing a problem report changes no library record and no list this screen
 * reads, so it invalidates nothing: the report lives in the reader's own bank
 * and the console answers it later.
 */
export function useReportObligationProblem(obligationId: string): UseMutationResult<ProblemReportCreated, unknown, ProblemReportBody> {
  return useMutation({ mutationFn: (body) => library.reportObligationProblem(obligationId, body) });
}

/** Playbook 10: the Instruments tab's own page size, like the obligations list. */
export const INSTRUMENT_PAGE = 20;

/** The route's maximum page: the instrument filter's options, so a picker is not cut at the tab's first page. */
export const INSTRUMENT_OPTIONS = 100;

/**
 * The Instruments tab (a page of 20) and the instrument filter's options (the route's
 * maximum of 100). `enabled` holds back a read only some states need.
 */
export function useInstruments(query: InstrumentQuery, limit: number = INSTRUMENT_PAGE, enabled = true): UseQueryResult<Page<Instrument>> {
  return useQuery({
    queryKey: libraryKeys.instruments(query, limit),
    queryFn: () => library.listInstruments({ ...query, limit, offset: 0 }),
    enabled,
  });
}

export function useInstrument(instrumentId: string): UseQueryResult<InstrumentDetail> {
  return useQuery({
    queryKey: libraryKeys.instrument(instrumentId),
    queryFn: () => library.getInstrument(instrumentId),
  });
}

/** "This looks wrong" on an instrument card; the report stays inside the reader's own bank, so nothing here invalidates. */
export function useReportInstrumentProblem(instrumentId: string): UseMutationResult<ProblemReportCreated, unknown, ProblemReportBody> {
  return useMutation({ mutationFn: (body) => library.reportInstrumentProblem(instrumentId, body) });
}

/**
 * The whole provision tree, every version of every unit included, so a
 * reader chooses one by its own chip rather than trusting today's date.
 * `asOf` only decides which version each node's `inForceVersion` names.
 */
export function useInstrumentProvisions(instrumentId: string, asOf = ''): UseQueryResult<ProvisionNode[]> {
  return useQuery({
    queryKey: libraryKeys.provisions(instrumentId, asOf),
    queryFn: () => library.listInstrumentProvisions(instrumentId, asOf),
  });
}

/** "Show what changed" on one provision, read only once the reader asks for it. */
export function useProvisionDiff(provisionId: string, lang: string, enabled: boolean): UseQueryResult<VersionDiff> {
  return useQuery({
    queryKey: libraryKeys.provisionDiff(provisionId, lang),
    queryFn: () => library.getProvisionDiff(provisionId, lang),
    enabled,
  });
}
