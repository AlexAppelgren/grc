'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { Facts, type Fact } from '@/components/inventory/ObligationPanels';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useAddObligationParticipant, useObligationParticipants, usePeople, useRemoveObligationParticipant, useTeams } from '@/features/participants/hooks';
import {
  addRefusals,
  PARTICIPANT_READ_PERMISSION,
  PARTICIPANTS_EDIT_PERMISSION,
  participantName,
  pickerOptions,
  presentParticipant,
  rowAction,
  type PickerOption,
} from '@/features/participants/participants-presentation';
import type { Participant } from '@/features/participants/types';
import { useRegisterEntry } from '@/features/register/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import { formatDate } from '@/shared/utils/format';

// "Participants" (COL-04; design/screens/tenant-obligation.html): the people
// and teams taking part in the bank's register entry for the obligation. The
// owners sit read-only above the list; each row names who added it. A member
// holding register.edit adds anyone and removes anyone; everyone may leave
// their own row. Taking part lists and notifies and grants nothing, so no
// step-up is asked, and every refusal is the server's, read by its code.

function AddDialog({ obligationId, onOpenChange }: { obligationId: string; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<PickerOption | null>(null);
  const people = usePeople(PARTICIPANT_READ_PERMISSION, true);
  const teams = useTeams(true);
  const add = useAddObligationParticipant(obligationId);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (picked === null) return;
    add.mutate(picked.kind === 'person' ? { userId: picked.value } : { teamKey: picked.value }, { onSuccess: () => onOpenChange(false) });
  };

  const options = people.data !== undefined && teams.data !== undefined ? pickerOptions(people.data, teams.data.items, query) : [];
  const failed = people.isError ? people.error : teams.isError ? teams.error : null;

  return (
    <Modal open onOpenChange={onOpenChange} title={t('obligationParticipants.addTitle')}>
      <form onSubmit={submit} noValidate aria-busy={add.isPending} data-participant-dialog="">
        <Field id="participant-find" label={t('obligationParticipants.find')} hint={t('obligationParticipants.findHint')}>
          <TextInput id="participant-find" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </Field>
        {failed !== null ? (
          <ProblemAlert error={failed} />
        ) : people.isPending || teams.isPending ? (
          <LoadingState rows={1} />
        ) : options.length === 0 ? (
          <p className="text-meta text-muted">{t('obligationParticipants.noMatch')}</p>
        ) : (
          <Rows role="radiogroup" aria-label={t('obligationParticipants.find')} className="max-h-[280px] overflow-auto">
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
                  <h3>{option.name}</h3>
                  <Meta>{t(option.kind === 'team' ? 'obligationParticipants.team' : 'obligationParticipants.person')}</Meta>
                </button>
              );
            })}
          </Rows>
        )}
        {add.isError ? <ProblemAlert error={add.error} codes={addRefusals(picked?.name ?? '', t)} /> : null}
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

export function ObligationParticipantsPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const meId = useSession().me?.user.id ?? null;
  const participants = useObligationParticipants(obligationId);
  const remove = useRemoveObligationParticipant(obligationId);
  const [adding, setAdding] = useState(false);
  const canAdd = permissions.includes(PARTICIPANTS_EDIT_PERMISSION);
  const items = participants.data?.items ?? [];

  return (
    <Panel title={t('obligationParticipants.heading')} data-participants-panel="">
      <Owners obligationId={obligationId} />
      {participants.isPending ? (
        <LoadingState rows={1} />
      ) : participants.isError ? (
        <ErrorState title={t('obligationParticipants.errorTitle')} onRetry={() => void participants.refetch()} />
      ) : items.length === 0 ? (
        <p className="text-meta text-muted" data-participants-empty="">
          {t('obligationParticipants.empty')}
        </p>
      ) : (
        <Rows>
          {items.map((participant) => (
            <ParticipantRow
              key={participant.id}
              participant={participant}
              action={rowAction(participant, meId, permissions)}
              busy={remove.isPending}
              onAct={() => remove.mutate(participant.id)}
            />
          ))}
        </Rows>
      )}
      {remove.isError ? <ProblemAlert error={remove.error} /> : null}
      <p className="mt-2.5 text-meta text-muted">{t('obligationParticipants.grantsNothing')}</p>
      {canAdd ? (
        <ButtonBar>
          <Button size="small" onClick={() => setAdding(true)}>
            {t('obligationParticipants.add')}
          </Button>
        </ButtonBar>
      ) : null}
      {adding ? <AddDialog obligationId={obligationId} onOpenChange={setAdding} /> : null}
    </Panel>
  );
}
