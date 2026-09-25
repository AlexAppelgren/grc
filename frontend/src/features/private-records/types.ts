// The bank's own queue (OWN-03, PRO-03, INV-07; D-89, ADR 0059). Every shape is an
// alias over the generated schemas in src/types/api.generated.ts.

import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

/** One proposal of the bank's own records, as the queue, approve and reject answer it. */
export type PrivateProposalRow = Schemas['PrivateProposalRow'];
export type PrivateProposalPage = Schemas['PrivateProposalPage'];
export type PrivateProposalApproveBody = Schemas['PrivateProposalApproveBody'];
export type PrivateProposalRejectBody = Schemas['PrivateProposalRejectBody'];

/** The one grant the queue needs (PRD section 6): Compliance officer and Approver hold it, no platform role or key scope does. */
export const PRIVATE_RECORDS_APPROVE = 'private_records.approve';
