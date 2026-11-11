'use client';

import { Facts } from '@/components/inventory/ObligationPanels';
import { AddParticipantDialog, ParticipantsPanel } from '@/components/participants/ParticipantsPanel';
import type { CasePanelProps } from '@/features/cases/types';
import { useAddCaseParticipant, useCaseParticipants, usePeople, useRemoveCaseParticipant } from '@/features/participants/hooks';
import { CASE_PARTICIPANT_READ_PERMISSION, CASE_PARTICIPANTS_EDIT_PERMISSION, caseAddRefusals } from '@/features/participants/participants-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Participants" on the change page (COL-04; design/screens/tenant-change.html):
// the people and teams taking part in the bank's case, in every status, a
// closed case's refusal included, which is the server's. A holder of
// cases.contribute adds and removes anyone.

/**
 * The one picker for a case: people and teams, or teams alone for the
 * assessment's contributor teams. Its submit never reaches the assessment
 * form it opens from (FormDialog stops it).
 */
export function AddCaseParticipantDialog({ changeId, teamsOnly = false, onOpenChange }: { changeId: string; teamsOnly?: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const people = usePeople(CASE_PARTICIPANT_READ_PERMISSION, !teamsOnly);
  const add = useAddCaseParticipant(changeId);
  return (
    <AddParticipantDialog
      title={t(teamsOnly ? 'caseParticipants.addTeamTitle' : 'obligationParticipants.addTitle')}
      findLabel={t(teamsOnly ? 'caseParticipants.findTeam' : 'obligationParticipants.find')}
      people={teamsOnly ? null : people}
      add={add}
      refusals={(name) => caseAddRefusals(name, t)}
      onOpenChange={onOpenChange}
    />
  );
}

export function CaseParticipantsPanel({ change, workflow }: CasePanelProps) {
  const t = useT();
  const participants = useCaseParticipants(change.id);
  const remove = useRemoveCaseParticipant(change.id);
  return (
    <ParticipantsPanel
      copy={{ heading: t('caseParticipants.heading'), errorTitle: t('caseParticipants.errorTitle'), empty: t('caseParticipants.empty'), grantsNothing: t('caseParticipants.grantsNothing') }}
      owners={
        workflow.owner === null ? null : (
          <div className="mb-3" data-participant-owners="">
            <Facts facts={[{ key: 'owner', label: t('caseParticipants.owner'), value: workflow.owner.name }]} />
          </div>
        )
      }
      participants={participants}
      remove={remove}
      editPermission={CASE_PARTICIPANTS_EDIT_PERMISSION}
      addDialog={(onOpenChange) => <AddCaseParticipantDialog changeId={change.id} onOpenChange={onOpenChange} />}
    />
  );
}
