import { api } from '@/shared/utils/api-client';

import type {
  RegisterApplicability,
  RegisterApplicabilityBody,
  RegisterApplicabilityMany,
  RegisterApplicabilityManyBody,
  RegisterAssessmentPage,
  RegisterDutyCompleteBody,
  RegisterDutyCompletion,
  RegisterDutyPage,
  RegisterEntityPatch,
  RegisterEntityStatus,
  RegisterEntry,
  RegisterGap,
  RegisterGapBody,
  RegisterGapPage,
  RegisterGapPatch,
  RegisterGapQuery,
  RegisterInternalItemPage,
  RegisterInternalLink,
  RegisterInternalLinkBody,
  RegisterInternalLinkPage,
  RegisterInterpretation,
  RegisterInterpretationBody,
  RegisterPageQuery,
  RegisterPatch,
  RegisterRiskAcceptanceBody,
  RegisterStatementOfApplicability,
  RegisterUnit,
  RegisterUnitBody,
  RegisterUnitPage,
  RegisterUnitPaste,
  RegisterUnitPasteBody,
  RegisterUnitPatch,
} from './types';

// Every register call the screens make, one thin typed wrapper per operation
// returning `.data` (playbook 6.1; backend/apps/register/api.py). A write to a
// versioned row takes the `version` last read, which the client sends as
// `If-Match`: a row someone changed in between answers 409 `stale_write` and
// nothing is merged. Approving a risk acceptance asks for the passkey step-up
// through the client's own prompt.

const V1 = '/api/v1';

const id = (value: string) => encodeURIComponent(value);
const obligation = (obligationId: string) => `${V1}/obligations/${id(obligationId)}`;

// The register entry and its legal entities (REG-02).

export async function getRegisterEntry(obligationId: string): Promise<RegisterEntry> {
  return (await api.get<RegisterEntry>(`${obligation(obligationId)}/register`)).data;
}

export async function updateRegister(obligationId: string, body: RegisterPatch, version: number): Promise<RegisterEntry> {
  return (await api.patch<RegisterEntry>(`${obligation(obligationId)}/register`, body, { version })).data;
}

export async function updateRegisterEntity(obligationId: string, orgUnitId: string, body: RegisterEntityPatch, version: number): Promise<RegisterEntityStatus> {
  return (await api.patch<RegisterEntityStatus>(`${obligation(obligationId)}/register/entities/${id(orgUnitId)}`, body, { version })).data;
}

// Applicability (REG-01): one person, a confirmation, no step-up (D-75).

export async function setApplicability(obligationId: string, body: RegisterApplicabilityBody, version: number): Promise<RegisterApplicability> {
  return (await api.put<RegisterApplicability>(`${obligation(obligationId)}/applicability`, body, { version })).data;
}

export async function setApplicabilityMany(body: RegisterApplicabilityManyBody): Promise<RegisterApplicabilityMany> {
  return (await api.post<RegisterApplicabilityMany>(`${V1}/applicability`, body)).data;
}

// Gaps and risk acceptance (REG-03).

export async function listObligationGaps(obligationId: string, page: RegisterPageQuery = {}): Promise<RegisterGapPage> {
  return (await api.get<RegisterGapPage>(`${obligation(obligationId)}/gaps`, { params: page })).data;
}

export async function createGap(obligationId: string, body: RegisterGapBody): Promise<RegisterGap> {
  return (await api.post<RegisterGap>(`${obligation(obligationId)}/gaps`, body)).data;
}

export async function listGaps(filters: RegisterGapQuery = {}, page: RegisterPageQuery = {}): Promise<RegisterGapPage> {
  return (await api.get<RegisterGapPage>(`${V1}/gaps`, { params: { ...filters, ...page } })).data;
}

export async function updateGap(gapId: string, body: RegisterGapPatch, version: number): Promise<RegisterGap> {
  return (await api.patch<RegisterGap>(`${V1}/gaps/${id(gapId)}`, body, { version })).data;
}

export async function requestRiskAcceptance(gapId: string, body: RegisterRiskAcceptanceBody): Promise<RegisterGap> {
  return (await api.post<RegisterGap>(`${V1}/gaps/${id(gapId)}/accept-risk`, body)).data;
}

export async function approveRiskAcceptance(gapId: string): Promise<RegisterGap> {
  return (await api.post<RegisterGap>(`${V1}/gaps/${id(gapId)}/accept-risk/approve`, {})).data;
}

export async function reopenGap(gapId: string): Promise<RegisterGap> {
  return (await api.post<RegisterGap>(`${V1}/gaps/${id(gapId)}/reopen`, {})).data;
}

// Assessment history and how we read the rule (REG-04).

export async function listAssessments(obligationId: string, page: RegisterPageQuery = {}): Promise<RegisterAssessmentPage> {
  return (await api.get<RegisterAssessmentPage>(`${obligation(obligationId)}/assessments`, { params: page })).data;
}

export async function getInterpretation(obligationId: string): Promise<RegisterInterpretation> {
  return (await api.get<RegisterInterpretation>(`${obligation(obligationId)}/interpretation`)).data;
}

export async function saveInterpretation(obligationId: string, body: RegisterInterpretationBody, version: number): Promise<RegisterInterpretation> {
  return (await api.put<RegisterInterpretation>(`${obligation(obligationId)}/interpretation`, body, { version })).data;
}

// Internal links (REG-05).

export async function listInternalLinks(obligationId: string, page: RegisterPageQuery = {}): Promise<RegisterInternalLinkPage> {
  return (await api.get<RegisterInternalLinkPage>(`${obligation(obligationId)}/internal-links`, { params: page })).data;
}

export async function addInternalLink(obligationId: string, body: RegisterInternalLinkBody): Promise<RegisterInternalLink> {
  return (await api.post<RegisterInternalLink>(`${obligation(obligationId)}/internal-links`, body)).data;
}

export async function removeInternalLink(linkId: string): Promise<void> {
  await api.delete(`${V1}/internal-links/${id(linkId)}`);
}

/** The bank's active items whose name or reference holds `q`, for the link dialog to pick. */
export async function listInternalItems(q: string, page: RegisterPageQuery = {}): Promise<RegisterInternalItemPage> {
  return (await api.get<RegisterInternalItemPage>(`${V1}/internal-items`, { params: { q, ...page } })).data;
}

// Statement of Applicability units under a standard's conformance obligation.

export async function listUnits(obligationId: string, entity?: string, page: RegisterPageQuery = {}): Promise<RegisterUnitPage> {
  return (await api.get<RegisterUnitPage>(`${obligation(obligationId)}/units`, { params: entity === undefined ? page : { entity, ...page } })).data;
}

export async function createUnit(obligationId: string, body: RegisterUnitBody): Promise<RegisterUnit> {
  return (await api.post<RegisterUnit>(`${obligation(obligationId)}/units`, body)).data;
}

export async function updateUnit(unitId: string, body: RegisterUnitPatch, version: number): Promise<RegisterUnit> {
  return (await api.patch<RegisterUnit>(`${V1}/units/${id(unitId)}`, body, { version })).data;
}

export async function removeUnit(unitId: string, version: number): Promise<void> {
  await api.delete(`${V1}/units/${id(unitId)}`, { version });
}

export async function pasteUnits(obligationId: string, body: RegisterUnitPasteBody): Promise<RegisterUnitPaste> {
  return (await api.post<RegisterUnitPaste>(`${obligation(obligationId)}/units/paste`, body)).data;
}

export async function getStatementOfApplicability(obligationId: string, entity: string, page: RegisterPageQuery = {}): Promise<RegisterStatementOfApplicability> {
  return (await api.get<RegisterStatementOfApplicability>(`${obligation(obligationId)}/statement-of-applicability`, { params: { entity, ...page } })).data;
}

// Recurring duties (REG-07).

export async function listDuties(obligationId: string, page: RegisterPageQuery = {}): Promise<RegisterDutyPage> {
  return (await api.get<RegisterDutyPage>(`${obligation(obligationId)}/duties`, { params: page })).data;
}

export async function completeDutyOccurrence(occurrenceId: string, body: RegisterDutyCompleteBody): Promise<RegisterDutyCompletion> {
  return (await api.post<RegisterDutyCompletion>(`${V1}/duty-occurrences/${id(occurrenceId)}/complete`, body)).data;
}
