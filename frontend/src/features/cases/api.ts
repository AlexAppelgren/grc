import { isAxiosError, type AxiosProgressEvent } from 'axios';

import { api } from '@/shared/utils/api-client';

import type {
  ActionBody,
  ActionPatch,
  AssessmentBody,
  Case,
  CaseAction,
  CaseActionPage,
  CaseEvidenceCreated,
  CaseEvidencePage,
  CasePage,
  CloseBody,
  EvidenceForm,
  NoteBody,
  PersonRef,
  ReasonBody,
  TriageBody,
} from './types';

// Thin typed wrappers returning `.data` (playbook 6.1), one per case workflow
// operation (CAS-02 to CAS-08). A case is addressed by its change: a bank has
// one case per change, and another bank's answers 404.
//
// `version` is the one the caller last read. The client sends it as
// `If-Match` on every write the contract checks it on, so a write over
// somebody else's is refused with 409 `stale_write` and never merged: the
// case's version on a workflow move and on an action added to it, the
// action's own version on an edit or a removal. Adding and removing evidence
// check no version (a piece of evidence is attached or removed whole, never
// edited), so none is sent there. A 403 `step_up_required` on the sign-off
// opens the shared passkey prompt inside the client and is sent again once.

const CHANGES = '/api/v1/changes';
const ACTIONS = '/api/v1/actions';
const EVIDENCE = '/api/v1/evidence';

const on = (changeId: string, path: string) => `${CHANGES}/${encodeURIComponent(changeId)}/${path}`;

// ---------------------------------------------------------------------------
// Triage, dismissal, restore and the one-person close (CAS-02)
// ---------------------------------------------------------------------------

export async function triageChange(changeId: string, body: TriageBody, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'triage'), body, { version })).data;
}

export async function dismissChange(changeId: string, body: ReasonBody, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'dismiss'), body, { version })).data;
}

export async function restoreChange(changeId: string, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'restore'), undefined, { version })).data;
}

export async function startAssessment(changeId: string, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'assessment/start'), undefined, { version })).data;
}

export async function closeWithoutAction(changeId: string, body: CloseBody, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'close'), body, { version })).data;
}

// ---------------------------------------------------------------------------
// The impact assessment (CAS-03)
// ---------------------------------------------------------------------------

export async function saveAssessment(changeId: string, body: AssessmentBody, version: number): Promise<Case> {
  return (await api.put<Case>(on(changeId, 'assessment'), body, { version })).data;
}

// ---------------------------------------------------------------------------
// Actions (CAS-04)
// ---------------------------------------------------------------------------

export async function listActions(changeId: string, page: CasePage = {}): Promise<CaseActionPage> {
  return (await api.get<CaseActionPage>(on(changeId, 'actions'), { params: page })).data;
}

/** The first action moves the case from assessing to implementing, so it carries the case's version. */
export async function addAction(changeId: string, body: ActionBody, caseVersion: number): Promise<CaseAction> {
  return (await api.post<CaseAction>(on(changeId, 'actions'), body, { version: caseVersion })).data;
}

export async function updateAction(actionId: string, body: ActionPatch, actionVersion: number): Promise<CaseAction> {
  return (await api.patch<CaseAction>(`${ACTIONS}/${encodeURIComponent(actionId)}`, body, { version: actionVersion })).data;
}

export async function deleteAction(actionId: string, actionVersion: number): Promise<void> {
  await api.delete(`${ACTIONS}/${encodeURIComponent(actionId)}`, { version: actionVersion });
}

// ---------------------------------------------------------------------------
// Evidence (CAS-05)
// ---------------------------------------------------------------------------

export async function listEvidence(changeId: string, page: CasePage = {}): Promise<CaseEvidencePage> {
  return (await api.get<CaseEvidencePage>(on(changeId, 'evidence'), { params: page })).data;
}

/** What the attach dialog sends: the form's fields, and a file's bytes when the kind is `file`. */
export interface EvidenceInput {
  kind: EvidenceForm['kind'];
  name: string;
  url?: string;
  file?: Blob;
}

/**
 * One multipart post: the bytes travel with the fields, and the server checks
 * the type and the size before it stores a byte. The client keeps no copy of
 * the allowed types, so a refusal is always the server's own words.
 */
export async function addEvidence(
  changeId: string,
  input: EvidenceInput,
  onUploadProgress?: (event: AxiosProgressEvent) => void,
): Promise<CaseEvidenceCreated> {
  const form = new FormData();
  form.append('kind', input.kind);
  form.append('name', input.name);
  if (input.url !== undefined) form.append('url', input.url);
  if (input.file !== undefined) form.append('file', input.file);
  return (await api.post<CaseEvidenceCreated>(on(changeId, 'evidence'), form, { onUploadProgress })).data;
}

/** A downloaded file: its bytes, and the name the server chose to save it under. */
export interface EvidenceDownload {
  content: Blob;
  fileName: string | null;
}

/**
 * The name from a `Content-Disposition` answer, `filename*` (RFC 5987, UTF-8)
 * before `filename`. The server strips control and direction characters and
 * ends the name in the checked type's extension, so the client never builds
 * a file name from what a person typed.
 */
export function fileNameOf(disposition: unknown): string | null {
  if (typeof disposition !== 'string') return null;
  const encoded = /filename\*=utf-8''([^;]+)/i.exec(disposition);
  if (encoded?.[1] !== undefined) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      return null;
    }
  }
  return /filename="((?:[^"\\]|\\.)*)"/i.exec(disposition)?.[1]?.replace(/\\(.)/g, '$1') ?? null;
}

/**
 * A checked file's bytes, streamed through the permission check and audited
 * per download. A refusal arrives as bytes too, so its problem body is read
 * back into JSON before it is thrown, and the panel branches on its `code`.
 */
export async function downloadEvidence(evidenceId: string): Promise<EvidenceDownload> {
  try {
    const response = await api.get<Blob>(`${EVIDENCE}/${encodeURIComponent(evidenceId)}/download`, { responseType: 'blob' });
    return { content: response.data, fileName: fileNameOf(response.headers['content-disposition']) };
  } catch (error) {
    const response = isAxiosError(error) ? error.response : undefined;
    if (response?.data instanceof Blob) {
      try {
        response.data = JSON.parse(await response.data.text()) as unknown;
      } catch {
        response.data = {};
      }
    }
    throw error;
  }
}

export async function removeEvidence(evidenceId: string): Promise<void> {
  await api.delete(`${EVIDENCE}/${encodeURIComponent(evidenceId)}`);
}

// ---------------------------------------------------------------------------
// Sign-off (CAS-06)
// ---------------------------------------------------------------------------

export async function requestSignoff(changeId: string, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'signoff/request'), undefined, { version })).data;
}

export async function approveSignoff(changeId: string, body: NoteBody, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'signoff/approve'), body, { version })).data;
}

export async function sendBackSignoff(changeId: string, body: NoteBody, version: number): Promise<Case> {
  return (await api.post<Case>(on(changeId, 'signoff/send-back'), body, { version })).data;
}

// ---------------------------------------------------------------------------
// The case file (CAS-07)
// ---------------------------------------------------------------------------

/** The whole case as plain text in the reader's language, as the server wrote it. */
export async function getCaseFile(changeId: string): Promise<string> {
  return (await api.get<string>(on(changeId, 'case-file'), { responseType: 'text' })).data;
}

// ---------------------------------------------------------------------------
// c9-fe-triage-assessment: who may own a case
// ---------------------------------------------------------------------------

/**
 * The bank's active members whose roles hold `permission`, by name: an owner
 * picker offers only people the triage would accept (`cases.work`).
 */
export async function listPeople(permission: string): Promise<PersonRef[]> {
  return (await api.get<PersonRef[]>('/api/v1/reference/people', { params: { permission } })).data;
}
