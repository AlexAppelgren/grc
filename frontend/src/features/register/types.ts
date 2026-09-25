import type { components } from '@/types/api.generated';

// The register's shapes as the API sends them (openapi.json, generated): the
// screens read these and nothing narrower, so a contract change fails the
// typecheck here rather than on a screen.

type Schemas = components['schemas'];

export type Applicability = Schemas['RegisterEntry']['applicability'];
export type RegisterVocabRef = Schemas['RegisterVocabRef'];
export type RegisterEntry = Schemas['RegisterEntry'];
export type RegisterEntityStatus = Schemas['RegisterEntityStatus'];
export type RegisterPatch = Schemas['RegisterPatch'];
export type RegisterEntityPatch = Schemas['RegisterEntityPatch'];
export type RegisterApplicability = Schemas['RegisterApplicability'];
export type RegisterApplicabilityBody = Schemas['RegisterApplicabilityBody'];
export type RegisterApplicabilityMany = Schemas['RegisterApplicabilityMany'];
export type RegisterApplicabilityManyBody = Schemas['RegisterApplicabilityManyBody'];
export type RegisterGap = Schemas['RegisterGap'];
export type RegisterGapPage = Schemas['RegisterGapPage'];
export type RegisterGapBody = Schemas['RegisterGapBody'];
export type RegisterGapPatch = Schemas['RegisterGapPatch'];
export type RegisterGapQuery = Schemas['RegisterGapQuery'];
export type RegisterRiskAcceptanceBody = Schemas['RegisterRiskAcceptanceBody'];
export type RegisterAssessmentPage = Schemas['RegisterAssessmentPage'];
export type RegisterInterpretation = Schemas['RegisterInterpretation'];
export type RegisterInterpretationBody = Schemas['RegisterInterpretationBody'];
export type RegisterInternalLink = Schemas['RegisterInternalLink'];
export type RegisterInternalLinkPage = Schemas['RegisterInternalLinkPage'];
export type RegisterInternalLinkBody = Schemas['RegisterInternalLinkBody'];
export type RegisterUnit = Schemas['RegisterUnit'];
export type RegisterUnitPage = Schemas['RegisterUnitPage'];
export type RegisterUnitBody = Schemas['RegisterUnitBody'];
export type RegisterUnitPatch = Schemas['RegisterUnitPatch'];
export type RegisterUnitPaste = Schemas['RegisterUnitPaste'];
export type RegisterUnitPasteBody = Schemas['RegisterUnitPasteBody'];
export type RegisterStatementOfApplicability = Schemas['RegisterStatementOfApplicability'];
export type RegisterDutyPage = Schemas['RegisterDutyPage'];
export type RegisterDutyCompleteBody = Schemas['RegisterDutyCompleteBody'];
export type RegisterDutyCompletion = Schemas['RegisterDutyCompletion'];

/** One page of a register list: `limit` 20 by default and 100 at most, `offset` from 0. */
export interface RegisterPageQuery {
  limit?: number;
  offset?: number;
}
