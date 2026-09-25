import type { ComponentType } from 'react';

import { closeKindOf } from '@/features/cases/case-presentation';
import type { CasePanelProps, CaseWorkflow } from '@/features/cases/types';

import { ActionsPanel } from './ActionsPanel';
import { AssessmentPanel } from './AssessmentPanel';
import { CaseFilePanel } from './CaseFilePanel';
import { EvidencePanel } from './EvidencePanel';
import { SignoffPanel } from './SignoffPanel';
import { TriagePanel } from './TriagePanel';

// The case's work on the change page (design/screens/tenant-change.html, the
// case panels' "Shown while" column; CAS-02 to CAS-07). The one place that
// decides which panel a case shows, from its fixed category and, once closed,
// from its close reason's fixed kind. What each panel then offers is its own,
// from the case's `allowedTransitions` and the reader's permissions: nothing
// here restates the state machine's moves.

export type CasePanelKey = 'triage' | 'assessment' | 'actions' | 'evidence' | 'signoff' | 'caseFile';

const WORK: readonly CasePanelKey[] = ['assessment', 'actions', 'evidence'];

/**
 * The panels a case shows, in the card's order. Triage holds the next step
 * and the one-person close (assigned, assessing) and Move back to triage, so
 * a dismissed case and one closed by one person return to it; a signed-off
 * case ends on its sign-off, with no way back. The case file is there in
 * every status.
 */
export function casePanelsFor(workflow: Pick<CaseWorkflow, 'category' | 'closeReason' | 'dismissedReason'>): CasePanelKey[] {
  switch (workflow.category) {
    case 'new':
    case 'assigned':
    case 'dismissed':
      return ['triage', 'caseFile'];
    case 'assessing':
      return ['triage', ...WORK, 'caseFile'];
    case 'implementing':
    case 'signoff':
      return [...WORK, 'signoff', 'caseFile'];
    case 'closed': {
      const kind = closeKindOf(workflow);
      if (kind === 'signed_off') return [...WORK, 'signoff', 'caseFile'];
      if (kind === 'no_action' || kind === 'not_applicable') return ['triage', ...WORK, 'caseFile'];
      return [...WORK, 'caseFile'];
    }
  }
}

const PANELS: Record<CasePanelKey, ComponentType<CasePanelProps>> = {
  triage: TriagePanel,
  assessment: AssessmentPanel,
  actions: ActionsPanel,
  evidence: EvidencePanel,
  signoff: SignoffPanel,
  caseFile: CaseFilePanel,
};

export function CaseWorkPanels({ change, workflow }: CasePanelProps) {
  return (
    <div data-case-panels={workflow.category}>
      {casePanelsFor(workflow).map((key) => {
        const Panel = PANELS[key];
        return <Panel key={key} change={change} workflow={workflow} />;
      })}
    </div>
  );
}
