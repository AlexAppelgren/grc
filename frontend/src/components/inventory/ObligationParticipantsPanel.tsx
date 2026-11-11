'use client';

import { Facts, type Fact } from '@/components/inventory/ObligationPanels';
import { AddParticipantDialog, ParticipantsPanel } from '@/components/participants/ParticipantsPanel';
import { useAddObligationParticipant, useObligationParticipants, usePeople, useRemoveObligationParticipant } from '@/features/participants/hooks';
import { addRefusals, PARTICIPANT_READ_PERMISSION, PARTICIPANTS_EDIT_PERMISSION } from '@/features/participants/participants-presentation';
import { useRegisterEntry } from '@/features/register/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Participants" (COL-04; design/screens/tenant-obligation.html): the people
// and teams taking part in the bank's register entry for the obligation. A
// member holding register.edit adds and removes anyone.

function Owners({ obligationId }: { obligationId: string }) {
  const t = useT();
  // The owners come with the register entry; until it can be read the list
  // stands on its own, since who takes part does not depend on them.
  const entry = useRegisterEntry(obligationId);
  if (entry.data === undefined) return null;
  const facts: Fact[] = [];
  if (entry.data.firstLineOwner !== null) facts.push({ key: 'owner', label: t('obligationParticipants.firstLineOwner'), value: entry.data.firstLineOwner.name });
  if (entry.data.complianceContact !== null) facts.push({ key: 'contact', label: t('obligationParticipants.complianceContact'), value: entry.data.complianceContact.name });
  if (facts.length === 0) return null;
  return (
    <div className="mb-3" data-participant-owners="">
      <Facts facts={facts} />
    </div>
  );
}

function AddDialog({ obligationId, onOpenChange }: { obligationId: string; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const people = usePeople(PARTICIPANT_READ_PERMISSION, true);
  const add = useAddObligationParticipant(obligationId);
  return (
    <AddParticipantDialog
      title={t('obligationParticipants.addTitle')}
      findLabel={t('obligationParticipants.find')}
      people={people}
      add={add}
      refusals={(name) => addRefusals(name, t)}
      onOpenChange={onOpenChange}
    />
  );
}

export function ObligationParticipantsPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const participants = useObligationParticipants(obligationId);
  const remove = useRemoveObligationParticipant(obligationId);
  return (
    <ParticipantsPanel
      copy={{
        heading: t('obligationParticipants.heading'),
        errorTitle: t('obligationParticipants.errorTitle'),
        empty: t('obligationParticipants.empty'),
        grantsNothing: t('obligationParticipants.grantsNothing'),
      }}
      owners={<Owners obligationId={obligationId} />}
      participants={participants}
      remove={remove}
      editPermission={PARTICIPANTS_EDIT_PERMISSION}
      addDialog={(onOpenChange) => <AddDialog obligationId={obligationId} onOpenChange={onOpenChange} />}
    />
  );
}
