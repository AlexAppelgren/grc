import type { ChangeDetail } from '@/features/watch/api';
import type { components } from '@/types/api.generated';

// The case workflow's shapes (CAS-02 to CAS-08), every one the generated
// contract's, never a hand-written copy: a contract change is a type error
// here rather than a wrong panel.

type Schemas = components['schemas'];

/** The seven fixed categories the state machine reads; a bank's sub-status sits inside one. */
export type CaseCategory = Schemas['CasesCase']['status'];

/** The case as every workflow write answers it. */
export type Case = Schemas['CasesCase'];

/** The case as the change page reads it, with its workflow block (`GET /changes/{changeId}`). */
export type CaseWorkflow = Schemas['WatchCaseWorkflow'];

/** A value of one of the bank's own lists: key, kind and label. */
export type CaseVocabularyRef = Schemas['CasesVocabularyRef'];
export type CaseAssessment = Schemas['CasesAssessment'];
export type CaseAction = Schemas['CasesAction'];
export type CaseActionPage = Schemas['CasesActionPage'];
export type CaseEvidence = Schemas['CasesEvidence'];
export type CaseEvidencePage = Schemas['CasesEvidencePage'];
export type CaseEvidenceCreated = Schemas['CasesEvidenceCreated'];

export type ScanState = CaseEvidence['scanState'];
export type EvidenceKind = CaseEvidence['kind'];

export type TriageBody = Schemas['CasesTriageBody'];
export type ReasonBody = Schemas['CasesReasonBody'];
export type CloseBody = Schemas['CasesCloseBody'];
export type NoteBody = Schemas['CasesNoteBody'];
export type AssessmentBody = Schemas['CasesAssessmentBody'];
export type ActionBody = Schemas['CasesActionBody'];
export type ActionPatch = Schemas['CasesActionPatch'];
export type EvidenceForm = Schemas['CasesEvidenceForm'];

/**
 * The fixed kinds a close reason row sits in: a second person signed it off,
 * or one person closed it because it needs no work or does not apply.
 */
export type CloseReasonKind = 'signed_off' | 'no_action' | 'not_applicable';

/** One page of a case's list; the route's own default and cap apply. */
export interface CasePage {
  limit?: number;
  offset?: number;
}

/**
 * What the change page hands every case panel: the change it sits on and the
 * bank's case with its workflow block, never null here, because a change
 * without a case mounts no panel.
 */
export interface CasePanelProps {
  change: ChangeDetail;
  workflow: CaseWorkflow;
}
