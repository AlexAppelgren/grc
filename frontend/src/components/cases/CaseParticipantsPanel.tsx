'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { Facts } from '@/components/inventory/ObligationPanels';
import type { CasePanelProps } from '@/features/cases/types';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useAddCaseParticipant, useCaseParticipants, usePeople, useRemoveCaseParticipant, useTeams } from '@/features/participants/hooks';
import {
  CASE_PARTICIPANT_READ_PERMISSION,
  CASE_PARTICIPANTS_EDIT_PERMISSION,
  caseAddRefusals,
  participantName,
  pickerOptions,
  presentParticipant,
  rowAction,
  type PickerOption,
} from '@/features/participants/participants-presentation';
import type { Participant } from '@/features/participants/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import { formatDate } from '@/shared/utils/format';

// "Participants" on the change page (COL-04; design/screens/tenant-change.html):
// the people and teams taking part in the bank's case, in every status. The
// owner sits read-only above the list and each row names who added it. A
// holder of cases.contribute adds anyone and removes anyone; everyone may
// leave their own row. Taking part lists and notifies and grants nothing, so
// no step-up is asked, and every refusal, a closed case's included, is the
// server's, read by its code and shown in place.

/**
 * The one picker for a case: people and teams, or teams alone for the
 * assessment's contributor teams. Each pick is one add call (D-20).
 */
export function AddCaseParticipantDialog({ changeId, teamsOnly = false, onOpenChange }: { changeId: string; teamsOnly?: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<PickerOption | null>(null);
  const people = usePeople(CASE_PARTICIPANT_READ_PERMISSION, !teamsOnly);
  const teams = useTeams(true);
  const add = useAddCaseParticipant(changeId);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    // The dialog is portalled, but React still bubbles its submit to the assessment form it opens from.
    event.stopPropagation();
    if (picked === null) return;
    add.mutate(picked.kind === 'person' ? { userId: picked.value } : { teamKey: picked.value }, { onSuccess: () => onOpenChange(false) });
  };

  const peopleList = teamsOnly ? [] : people.data;
  const options = peopleList !== undefined && teams.data !== undefined ? pickerOptions(peopleList, teams.data.items, query) : [];
  const failed = !teamsOnly && people.isError ? people.error : teams.isError ? teams.error : null;
  const loading = (!teamsOnly && people.isPending) || teams.isPending;
  const findLabel = t(teamsOnly ? 'caseParticipants.findTeam' : 'obligationParticipants.find');

  return (
    <Modal open onOpenChange={onOpenChange} title={t(teamsOnly ? 'caseParticipants.addTeamTitle' : 'obligationParticipants.addTitle')}>
      <form onSubmit={submit} noValidate aria-busy={add.isPending} data-participant-dialog="">
        <Field id="case-participant-find" label={findLabel} hint={t('obligationParticipants.findHint')}>
          <TextInput id="case-participant-find" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </Field>
        {failed !== null ? (
          <ProblemAlert error={failed} />
        ) : loading ? (
          <LoadingState rows={1} />
        ) : options.length === 0 ? (
          <p className="text-meta text-muted">{t('obligationParticipants.noMatch')}</p>
        ) : (
          <Rows role="radiogroup" aria-label={findLabel} className="max-h-[280px] overflow-auto">
            {options.map((option) => {
              const selected = picked?.kind === option.kind && picked.value === option.value;
              return (
                <button
                  key={`${option.kind}:${option.value}`}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setPicked(option)}
                  className={cn('rounded-card border px-4 py-3 text-left', selected ? 'border-fg' : 'border-line')}
                  data-pick-participant={option.value}
                >
                  <span className="block font-medium">{option.name}</span>
                  <span className="block text-meta text-muted">{t(option.kind === 'team' ? 'obligationParticipants.team' : 'obligationParticipants.person')}</span>
                </button>
              );
            })}
          </Rows>
        )}
        {add.isError ? <ProblemAlert error={add.error} codes={caseAddRefusals(picked?.name ?? '', t)} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={picked === null || add.isPending}>
            {t('obligationParticipants.addConfirm')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function ParticipantRow({ participant, action, onAct, busy }: { participant: Participant; action: 'leave' | 'remove' | null; onAct: () => void; busy: boolean }) {
  const t = useT();
  const ctx = useFormatContext();
  const meId = useSession().me?.user.id ?? null;
  return (
    <Row data-participant-id={participant.id}>
      <h3>{participantName(participant)}</h3>
      <Meta className="mt-1">
        <PillRow pills={presentParticipant(participant, meId, t)} />
        {participant.team === null ? null : <span>{t('obligationParticipants.team')}</span>}
        <span>{t('obligationParticipants.addedBy', { date: formatDate(participant.addedAt, ctx), name: participant.addedBy.name })}</span>
      </Meta>
      {action === null ? null : (
        <Button variant="ghost" size="small" className="mt-2" disabled={busy} onClick={onAct}>
          {t(action === 'leave' ? 'obligationParticipants.leave' : 'obligationParticipants.remove')}
        </Button>
      )}
    </Row>
  );
}

export function CaseParticipantsPanel({ change, workflow }: CasePanelProps) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const meId = useSession().me?.user.id ?? null;
  const participants = useCaseParticipants(change.id);
  const remove = useRemoveCaseParticipant(change.id);
  const [adding, setAdding] = useState(false);
  const items = participants.data?.items ?? [];

  return (
    <Panel title={t('caseParticipants.heading')} data-participants-panel="">
      {workflow.owner === null ? null : (
        <div className="mb-3" data-participant-owners="">
          <Facts facts={[{ key: 'owner', label: t('caseParticipants.owner'), value: workflow.owner.name }]} />
        </div>
      )}
      {participants.isPending ? (
        <LoadingState rows={1} />
      ) : participants.isError ? (
        <ErrorState title={t('caseParticipants.errorTitle')} onRetry={() => void participants.refetch()} />
      ) : items.length === 0 ? (
        <p className="text-meta text-muted" data-participants-empty="">
          {t('caseParticipants.empty')}
        </p>
      ) : (
        <Rows>
          {items.map((participant) => (
            <ParticipantRow
              key={participant.id}
              participant={participant}
              action={rowAction(participant, meId, permissions, CASE_PARTICIPANTS_EDIT_PERMISSION)}
              busy={remove.isPending}
              onAct={() => remove.mutate(participant.id)}
            />
          ))}
        </Rows>
      )}
      {remove.isError ? <ProblemAlert error={remove.error} /> : null}
      <p className="mt-2.5 text-meta text-muted">{t('caseParticipants.grantsNothing')}</p>
      {permissions.includes(CASE_PARTICIPANTS_EDIT_PERMISSION) ? (
        <ButtonBar>
          <Button size="small" onClick={() => setAdding(true)}>
            {t('obligationParticipants.add')}
          </Button>
        </ButtonBar>
      ) : null}
      {adding ? <AddCaseParticipantDialog changeId={change.id} onOpenChange={setAdding} /> : null}
    </Panel>
  );
}
