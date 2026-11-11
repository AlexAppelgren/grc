'use client';

import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { FormDialog } from '@/components/ui/Dialogs';
import { Field, TextInput } from '@/components/ui/Field';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { LoadingState, ProblemAlert, QueryState } from '@/components/ui/States';
import { useFormatContext, useSession } from '@/features/identity/hooks';
import { useTeams } from '@/features/participants/hooks';
import { participantName, pickerOptions, presentParticipant, rowAction, type PickerOption } from '@/features/participants/participants-presentation';
import type { Participant, ParticipantInput, ParticipantPage, PersonRef } from '@/features/participants/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import { formatDate } from '@/shared/utils/format';

// "Participants" (COL-04) on the obligation page and the change page: the
// people and teams taking part in the bank's register entry or case. The
// owners sit read-only above the list and each row names who added it. A
// holder of the record's edit permission adds anyone and removes anyone;
// everyone may leave their own row. Taking part lists and notifies and grants
// nothing, so no step-up is asked, and every refusal is the server's, read by
// its code and shown in place.

/**
 * The picker: people and teams, or teams alone (`people` null). Each pick is
 * one add call (D-20).
 */
export function AddParticipantDialog({
  title,
  findLabel,
  people,
  add,
  refusals,
  onOpenChange,
}: {
  title: string;
  findLabel: string;
  people: UseQueryResult<PersonRef[]> | null;
  add: UseMutationResult<Participant, unknown, ParticipantInput>;
  refusals: (name: string) => Readonly<Record<string, string>>;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<PickerOption | null>(null);
  const teams = useTeams(true);
  const submit = () => {
    if (picked === null) return;
    add.mutate(picked.kind === 'person' ? { userId: picked.value } : { teamKey: picked.value }, { onSuccess: () => onOpenChange(false) });
  };
  const peopleList = people === null ? [] : people.data;
  const options = peopleList !== undefined && teams.data !== undefined ? pickerOptions(peopleList, teams.data.items, query) : [];
  const failed = people?.isError ? people.error : teams.isError ? teams.error : null;
  const loading = (people?.isPending ?? false) || teams.isPending;

  return (
    <FormDialog
      title={title}
      submitLabel={t('obligationParticipants.addConfirm')}
      pending={add.isPending}
      submitDisabled={picked === null}
      error={add.error}
      codes={refusals(picked?.name ?? '')}
      onSubmit={submit}
      onClose={() => onOpenChange(false)}
      formProps={{ 'data-participant-dialog': '' }}
    >
      <Field id="participant-find" label={findLabel} hint={t('obligationParticipants.findHint')}>
        <TextInput id="participant-find" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
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
    </FormDialog>
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
          {t(action === 'leave' ? 'obligationParticipants.leave' : 'common.remove')}
        </Button>
      )}
    </Row>
  );
}

export function ParticipantsPanel({
  copy,
  owners,
  participants,
  remove,
  editPermission,
  addDialog,
}: {
  copy: { heading: string; errorTitle: string; empty: string; grantsNothing: string };
  owners: ReactNode;
  participants: UseQueryResult<ParticipantPage>;
  remove: UseMutationResult<void, unknown, string>;
  editPermission: string;
  addDialog: (onOpenChange: (open: boolean) => void) => ReactNode;
}) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const meId = useSession().me?.user.id ?? null;
  const [adding, setAdding] = useState(false);

  return (
    <Panel title={copy.heading} data-participants-panel="">
      {owners}
      <QueryState query={participants} rows={1} errorTitle={copy.errorTitle}>
        {({ items }) =>
          items.length === 0 ? (
            <p className="text-meta text-muted" data-participants-empty="">
              {copy.empty}
            </p>
          ) : (
            <Rows>
              {items.map((participant) => (
                <ParticipantRow
                  key={participant.id}
                  participant={participant}
                  action={rowAction(participant, meId, permissions, editPermission)}
                  busy={remove.isPending}
                  onAct={() => remove.mutate(participant.id)}
                />
              ))}
            </Rows>
          )
        }
      </QueryState>
      {remove.isError ? <ProblemAlert error={remove.error} /> : null}
      <p className="mt-2.5 text-meta text-muted">{copy.grantsNothing}</p>
      {permissions.includes(editPermission) ? (
        <ButtonBar>
          <Button size="small" onClick={() => setAdding(true)}>
            {t('obligationParticipants.add')}
          </Button>
        </ButtonBar>
      ) : null}
      {adding ? addDialog(setAdding) : null}
    </Panel>
  );
}
