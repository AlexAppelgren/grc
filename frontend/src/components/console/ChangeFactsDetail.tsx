'use client';

import { useState } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, Select } from '@/components/ui/Field';
import { Notice } from '@/components/ui/Notice';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert, StatusLine } from '@/components/ui/States';
import {
  authorityAndPublished,
  factProvenance,
  firstSeen,
  linkProvenance,
  presentConsoleChange,
  type ChangeFact,
  type ConsoleChangeRow,
  type ObligationLink,
} from '@/features/console-watch/change-facts';
import {
  confirmationOf,
  linksWithout,
  useConfirmCuration,
  useConsoleChange,
  useCorrectChangeFacts,
  useScopeTermIds,
  useSetObligationLinks,
  type ConfirmPart,
} from '@/features/console-watch/change-facts-detail';
import { useFormatContext } from '@/features/identity/hooks';
import { slotTone } from '@/features/shared/tone-by-kind';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import type { Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';

// One change in the console (design/screens/console-change-facts.html,
// WAT-03, WAT-04): what an agent put forward about a reform, each fact with
// its confidence and its suggestion marker, and the corrections a library
// editor may make. The shared library only: a bank's case, its urgency, its
// footprint verdict and its "So what?" are its own and are neither read nor
// shown here.
//
// Confirming is D-74's: an independent agent confirms most facts, and a
// person holding proposals.review may confirm one instead, with a passkey the
// route asks for. A fact a machine confirmed names both agents and never
// reads as a person's; a person's reads confirmed by a person.

const UNKNOWN_KEY = 'unknown_key';

/** A refusal of a confirmation, read from its code and never from the sentence. */
function confirmCodes(t: Translate): Record<string, string> {
  return {
    own_suggestion: t('console.changeFacts.ownSuggestion'),
    validation_error: t('console.changeFacts.changedMeanwhile'),
    step_up_required: t('problem.stepUpCancelled'),
  };
}

function Fact({ name, pills, provenance, action }: { name: string; pills: readonly { key: string; label: string; tone: (typeof slotTone)[keyof typeof slotTone]; order: number }[]; provenance: string; action?: React.ReactNode }) {
  return (
    <div className="grid items-start gap-2 border-b border-line py-3 last:border-b-0 md:grid-cols-[132px_minmax(0,1fr)_auto] md:gap-x-4" data-fact={name}>
      <div className="font-medium">{name}</div>
      <div className="grid min-w-0 gap-1.5">
        {pills.length > 0 ? <PillRow pills={pills} /> : null}
        <p className="text-meta text-muted">{provenance}</p>
      </div>
      {action}
    </div>
  );
}

function CorrectType({ change, onDone }: { change: ConsoleChangeRow; onDone: () => void }) {
  const t = useT();
  const types = useVocabularyValues('change_type');
  const correct = useCorrectChangeFacts(change.id);
  const [key, setKey] = useState(change.changeType.ref.key);
  return (
    <Panel title={t('console.changeFacts.fact.type')} data-correct-type="">
      <Field id="change-type" label={t('console.changeFacts.fact.type')} hint={t('console.changeFacts.typeHint')}>
        <Select id="change-type" value={key} onChange={(e) => setKey(e.target.value)}>
          {types.data?.map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </Select>
      </Field>
      {/* The valid keys are the picker above, which is the vocabulary itself:
          the refusal is read from its code and never from the sentence. */}
      {correct.isError ? <ProblemAlert error={correct.error} codes={{ [UNKNOWN_KEY]: t('console.changeFacts.unknownKey') }} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={onDone} disabled={correct.isPending}>
          {t('common.cancel')}
        </Button>
        <Button disabled={correct.isPending} onClick={() => correct.mutate({ changeType: key }, { onSuccess: onDone })}>
          {t('console.changeFacts.saveType')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

function CorrectFlags({ change, onDone }: { change: ConsoleChangeRow; onDone: () => void }) {
  const t = useT();
  const flags = useVocabularyValues('flag');
  const correct = useCorrectChangeFacts(change.id);
  const [keys, setKeys] = useState<string[]>(change.flags.map((flag) => flag.ref.key));
  return (
    <Panel title={t('console.changeFacts.fact.flags')} data-correct-flags="">
      <CheckGroup legend={t('console.changeFacts.fact.flags')} hint={t('console.changeFacts.flagsHint')}>
        {flags.data?.map((row) => (
          <CheckRow
            key={row.key}
            id={`flag-${row.key}`}
            label={row.label}
            checked={keys.includes(row.key)}
            onChange={(checked) => setKeys((current) => (checked ? [...current, row.key] : current.filter((k) => k !== row.key)))}
          />
        ))}
      </CheckGroup>
      {correct.isError ? <ProblemAlert error={correct.error} codes={{ [UNKNOWN_KEY]: t('console.changeFacts.unknownKey') }} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={onDone} disabled={correct.isPending}>
          {t('common.cancel')}
        </Button>
        <Button disabled={correct.isPending} onClick={() => correct.mutate({ flags: keys }, { onSuccess: onDone })}>
          {t('console.changeFacts.saveFlags')}
        </Button>
      </ButtonBar>
    </Panel>
  );
}

function LinkRow({ change, link }: { change: ConsoleChangeRow; link: ObligationLink }) {
  const t = useT();
  const set = useSetObligationLinks(change.id);
  const confirm = useConfirmCuration(change.id);
  const pending = set.isPending || confirm.isPending;
  return (
    <Row data-obligation-id={link.obligationId}>
      <PillRow
        pills={[
          { key: `instrument:${link.obligationId}`, label: link.instrumentShortName, tone: slotTone.instrument, order: 10 },
          !link.confirmed
            ? { key: 'suggested', label: t('console.changeFacts.suggestedMarker'), tone: slotTone.suggested, order: 20 }
            : link.confirmedOrigin === 'user'
              ? { key: 'confirmed', label: t('console.changeFacts.confirmed'), tone: slotTone.confirmed, order: 20 }
              : { key: 'machine-confirmed', label: t('watch.row.machineConfirmed'), tone: slotTone.machineConfirmed, order: 20 },
        ]}
      />
      <h3 className="mt-1.5 mb-1 font-semibold">{link.title}</h3>
      <Meta>
        <span className="font-mono">{link.refLabel}</span>
        <span>{linkProvenance(link, t)}</span>
      </Meta>
      {set.isError ? <ProblemAlert error={set.error} /> : null}
      {confirm.isError ? <ProblemAlert error={confirm.error} codes={confirmCodes(t)} /> : null}
      <ButtonBar>
        <Button variant="danger" size="small" disabled={pending} onClick={() => set.mutate(linksWithout(change.obligations, link.obligationId))}>
          {t('console.changeFacts.removeLink')}
        </Button>
        {link.confirmed ? null : (
          <Button size="small" disabled={pending} onClick={() => confirm.mutate({ flags: [], termIds: [], obligationIds: [link.obligationId] })}>
            {t('console.changeFacts.confirmLink')}
          </Button>
        )}
      </ButtonBar>
    </Row>
  );
}

type Correcting = 'type' | 'flags' | null;

function Detail({ change }: { change: ConsoleChangeRow }) {
  const t = useT();
  const ctx = useFormatContext();
  const [correcting, setCorrecting] = useState<Correcting>(null);
  const confirm = useConfirmCuration(change.id);
  const termIdOf = useScopeTermIds(change.terms.some((term) => term.suggested));
  const confirmButton = (part: ConfirmPart) => {
    const body = confirmationOf(change, part, termIdOf);
    const names = body.changeType !== undefined || [...(body.flags ?? []), ...(body.termIds ?? []), ...(body.obligationIds ?? [])].length > 0;
    return names ? (
      <Button size={part === 'rest' ? 'default' : 'small'} disabled={confirm.isPending} onClick={() => confirm.mutate(body)}>
        {t(part === 'rest' ? 'console.changeFacts.confirmRest' : 'console.changeFacts.confirm')}
      </Button>
    ) : null;
  };
  const actions = (which: Exclude<Correcting, null> | null, part: ConfirmPart) => (
    <ButtonBar className="mt-0">
      {which === null ? null : (
        <Button variant="outline" size="small" onClick={() => setCorrecting(which)}>
          {t('console.changeFacts.correct')}
        </Button>
      )}
      {confirmButton(part)}
    </ButtonBar>
  );
  const pillsOf = (facts: readonly ChangeFact[], tone: (typeof slotTone)[keyof typeof slotTone]) =>
    facts.map((fact, i) => ({ key: fact.ref.key, label: fact.ref.label, tone, order: i }));
  // One sentence for a set: the least confident member is what a reader needs
  // to know about the set as a whole.
  const setProvenance = (facts: readonly ChangeFact[], empty: string) =>
    facts.length === 0 ? empty : factProvenance([...facts].sort((a, b) => (a.confidence ?? 1) - (b.confidence ?? 1))[0]!, t);

  return (
    <>
      <BackLink href="/console/change-facts" label={t('console.changeFacts.backToList')} />
      <PillRow pills={presentConsoleChange(change, t)} />
      <h1 className="mt-1.5">{change.title}</h1>
      <Meta className="mt-1.5 mb-4 flex flex-wrap gap-x-3 gap-y-1">
        <span>{authorityAndPublished(change, t, ctx)}</span>
        <span>{firstSeen(change, t, ctx)}</span>
        <span className="font-mono">{t('console.changeFacts.stableKey', { key: change.stableKey })}</span>
      </Meta>
      <Notice>{t('console.changeFacts.explain')}</Notice>

      <Panel title={t('console.changeFacts.factsTitle')}>
        <Fact
          name={t('console.changeFacts.fact.type')}
          pills={[{ key: change.changeType.ref.key, label: change.changeType.ref.label, tone: slotTone.changeType, order: 0 }]}
          provenance={factProvenance(change.changeType, t)}
          action={actions('type', 'type')}
        />
        <Fact
          name={t('console.changeFacts.fact.flags')}
          pills={pillsOf(change.flags, slotTone.flag)}
          provenance={setProvenance(change.flags, t('console.changeFacts.noFlags'))}
          action={actions('flags', 'flags')}
        />
        <Fact
          name={t('console.changeFacts.fact.scope')}
          pills={pillsOf(change.terms, slotTone.scopeTerm)}
          provenance={setProvenance(change.terms, t('console.changeFacts.noScope'))}
          action={actions(null, 'scope')}
        />
        {confirm.isError ? <ProblemAlert error={confirm.error} codes={confirmCodes(t)} /> : null}
        <p className="mt-3 text-meta text-muted">{t('console.changeFacts.confirmHint')}</p>
        <ButtonBar>{confirmButton('rest')}</ButtonBar>
      </Panel>
      {correcting === 'type' ? <CorrectType change={change} onDone={() => setCorrecting(null)} /> : null}
      {correcting === 'flags' ? <CorrectFlags change={change} onDone={() => setCorrecting(null)} /> : null}

      <Panel title={t('console.changeFacts.obligationsTitle')}>
        <p className="mb-3 text-meta text-muted">{t('console.changeFacts.obligationsBody')}</p>
        {change.obligations.length === 0 ? (
          <StatusLine>{t('console.changeFacts.noObligations')}</StatusLine>
        ) : (
          <Rows data-obligation-links="">
            {change.obligations.map((link) => (
              <LinkRow key={link.obligationId} change={change} link={link} />
            ))}
          </Rows>
        )}
      </Panel>
    </>
  );
}

export function ChangeFactsDetail({ changeId }: { changeId: string }) {
  const t = useT();
  const change = useConsoleChange(changeId);
  if (change.isPending) return <LoadingState rows={3} />;
  if (change.isError) return <ErrorState title={t('console.changeFacts.changeErrorTitle')} onRetry={change.refetch} />;
  if (change.change === null) return <NotFoundScreen body={t('console.changeFacts.notFoundBody')} backHref="/console/change-facts" backLabel={t('console.changeFacts.backToList')} />;
  return <Detail change={change.change} />;
}
