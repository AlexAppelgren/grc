'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { PillRow } from '@/components/ui/PillRow';
import { ProblemAlert } from '@/components/ui/States';
import { usePasteUnits } from '@/features/register/hooks';
import { presentApplicability } from '@/features/register/register-presentation';
import type { Applicability, RegisterUnitPaste } from '@/features/register/types';
import type { MessageKey, Translate } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Paste units" (design/screens/tenant-obligation-units.html, frames 7 to 9;
// REG-08, REG-01, AC-REG1). The person pastes their own list, one unit per
// line: reference, tab, title, and optionally tab, a decision word and tab, a
// reason. The server's dry run says what each line would become and stores
// nothing; decisions are read here, since the paste itself carries only the
// reference and title. Creating asks once: every decision the paste carries is
// listed in one confirmation, then the units are created and the decisions set
// in one call. Without applicability.approve the decisions are left out and the
// dialog says so. There is no field for the standard's text.

type Decision = Exclude<Applicability, 'under_assessment'>;
type PasteProblem = NonNullable<RegisterUnitPaste['rows'][number]['problem']>;

export interface PastedLine {
  reference: string;
  title: string;
  decision: Decision | null;
  reason: string;
  /** The decision word as pasted, kept for the refusal that names it. */
  word: string;
  problem: 'decision' | 'reason' | null;
}

export interface DecisionWords {
  applies: string;
  doesNotApply: string;
}

/** Splits the pasted text into lines of reference, title, decision and reason; blank lines are skipped. */
export function parsePastedUnits(text: string, words: DecisionWords, withDecisions: boolean): PastedLine[] {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim() !== '')
    .map((line) => {
      const [reference = '', title = '', rawWord = '', rawReason = ''] = line.split('\t');
      const word = withDecisions ? rawWord.trim() : '';
      const reason = withDecisions ? rawReason.trim() : '';
      const lower = word.toLocaleLowerCase();
      const decision: Decision | null =
        lower === words.applies.toLocaleLowerCase() ? 'applies' : lower === words.doesNotApply.toLocaleLowerCase() ? 'not_applicable' : null;
      const problem = word !== '' && decision === null ? 'decision' : decision !== null && reason === '' ? 'reason' : null;
      return { reference, title, decision, reason, word, problem };
    });
}

const SERVER_REFUSAL: Record<PasteProblem, MessageKey> = {
  duplicate_reference: 'obligationUnits.refusedDuplicate',
  reference_exists: 'obligationUnits.refusedExists',
  reference_too_long: 'obligationUnits.refusedReferenceLong',
  title_too_long: 'obligationUnits.refusedTitleLong',
  empty_line: 'obligationUnits.refusedEmpty',
  reason_missing: 'obligationUnits.refusedReason',
};

interface CheckedLine extends PastedLine {
  line: number;
  why: string | null;
}

function refusal(pasted: PastedLine, problem: PasteProblem | null, entity: string, words: DecisionWords, t: Translate): string | null {
  if (problem !== null) return t(SERVER_REFUSAL[problem], { entity });
  if (pasted.problem === 'decision') return t('obligationUnits.refusedDecision', { value: pasted.word, ...words });
  if (pasted.problem === 'reason') return t('obligationUnits.refusedReason');
  return null;
}

const cell = 'border-b border-line px-2 py-1.5 text-left align-top';

export function PasteUnitsDialog({
  obligationId,
  entity,
  canDecide,
  open,
  onOpenChange,
  onCreated,
}: {
  obligationId: string;
  entity: { id: string; name: string };
  canDecide: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (count: number) => void;
}) {
  const t = useT();
  const paste = usePasteUnits(obligationId);
  const [text, setText] = useState('');
  const [step, setStep] = useState<'text' | 'dry' | 'confirm'>('text');
  const [checked, setChecked] = useState<CheckedLine[]>([]);
  const [leftOut, setLeftOut] = useState(false);
  const words: DecisionWords = { applies: t('obligationUnits.wordApplies'), doesNotApply: t('obligationUnits.wordDoesNotApply') };

  const ready = checked.filter((line) => line.why === null);
  const refused = checked.filter((line) => line.why !== null);
  const decisions = ready.filter((line) => line.decision !== null);
  const problemCodes = { scope_not_applicable: t('obligationUnits.problemScope', { entity: entity.name }), units_only_under_standards: t('obligationUnits.problemStandard') };

  /** Resets the dialog; says how many units were created when any were. */
  const finish = (count: number | null) => {
    if (count !== null) onCreated(count);
    setText('');
    setStep('text');
    setChecked([]);
    setLeftOut(false);
    paste.reset();
    onOpenChange(false);
  };
  const close = () => finish(null);

  const check = async (event: FormEvent) => {
    event.preventDefault();
    const lines = parsePastedUnits(text, words, canDecide);
    setLeftOut(!canDecide && parsePastedUnits(text, words, true).some((line) => line.word !== ''));
    const result = await paste.mutateAsync({ orgUnitId: entity.id, lines: lines.map(({ reference, title }) => ({ reference, title })), dryRun: true }).catch(() => null);
    if (result === null) return;
    setChecked(
      result.rows.flatMap((row, index) => {
        const line = lines[index];
        if (line === undefined) return [];
        const pasted = { ...line, reference: row.reference, title: row.title };
        return [{ ...pasted, line: row.line, why: refusal(pasted, row.problem ?? null, entity.name, words, t) }];
      }),
    );
    setStep('dry');
  };

  // One call: the units and the decisions their lines carry are stored together, all or none.
  const commit = async () => {
    const lines = ready.map(({ reference, title, decision, reason }) => (decision === null ? { reference, title } : { reference, title, applicability: decision, reason }));
    const result = await paste.mutateAsync({ orgUnitId: entity.id, lines, dryRun: false }).catch(() => null);
    if (result !== null) finish(result.created);
  };

  const title = step === 'text' ? t('obligationUnits.pasteTitle', { entity: entity.name }) : step === 'dry' ? t('obligationUnits.dryTitle') : t('obligationUnits.confirmTitle', { count: decisions.length, entity: entity.name });

  return (
    <Modal open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())} title={title}>
      {step === 'text' ? (
        <form onSubmit={(event) => void check(event)} noValidate aria-busy={paste.isPending}>
          <Field id="paste-units-text" label={t('obligationUnits.pasteField')} hint={canDecide ? t('obligationUnits.pasteHint', { ...words }) : t('obligationUnits.pasteHintNoDecisions')}>
            <TextArea id="paste-units-text" className="min-h-40 font-mono" aria-describedby="paste-units-text-hint" value={text} onChange={(event) => setText(event.target.value)} />
          </Field>
          {paste.isError ? <ProblemAlert error={paste.error} codes={problemCodes} /> : null}
          <ButtonBar>
            <Button variant="outline" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={text.trim() === '' || paste.isPending}>
              {t('obligationUnits.check')}
            </Button>
          </ButtonBar>
        </form>
      ) : step === 'dry' ? (
        <div data-paste-dry-run="">
          <p className="mb-3">{t('obligationUnits.dryBody')}</p>
          {leftOut ? <Notice tone="warn">{t('obligationUnits.decisionsLeftOut')}</Notice> : null}
          <h3 className="mb-2 font-medium">{t('obligationUnits.readyHeading', { count: ready.length })}</h3>
          {ready.length > 0 ? (
            <div className="mb-4 overflow-x-auto">
              <table className="w-full border-collapse text-meta" data-paste-ready="">
                <thead>
                  <tr>
                    <th className={cell}>{t('obligationUnits.columnLine')}</th>
                    <th className={cell}>{t('obligationUnits.columnReference')}</th>
                    <th className={cell}>{t('obligationUnits.columnTitle')}</th>
                    <th className={cell}>{t('obligationUnits.columnDecision')}</th>
                  </tr>
                </thead>
                <tbody>
                  {ready.map((line) => (
                    <tr key={line.line}>
                      <td className={cell}>{line.line}</td>
                      <td className={`${cell} font-mono`}>{line.reference}</td>
                      <td className={cell}>{line.title}</td>
                      <td className={cell}>{line.decision === null ? t('obligationUnits.noDecisionCell') : <PillRow pills={[presentApplicability(line.decision, t)]} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {refused.length > 0 ? (
            <>
              <h3 className="mb-2 font-medium">{t('obligationUnits.refusedHeading', { count: refused.length })}</h3>
              <div className="mb-4 overflow-x-auto">
                <table className="w-full border-collapse text-meta" data-paste-refused="">
                  <thead>
                    <tr>
                      <th className={cell}>{t('obligationUnits.columnLine')}</th>
                      <th className={cell}>{t('obligationUnits.columnReference')}</th>
                      <th className={cell}>{t('obligationUnits.columnWhy')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {refused.map((line) => (
                      <tr key={line.line}>
                        <td className={cell}>{line.line}</td>
                        <td className={`${cell} font-mono`}>{line.reference}</td>
                        <td className={cell}>{line.why}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
          {paste.isError ? <ProblemAlert error={paste.error} codes={problemCodes} /> : null}
          <ButtonBar>
            <Button
              variant="outline"
              onClick={() => {
                paste.reset();
                setStep('text');
              }}
            >
              {t('obligationUnits.backToText')}
            </Button>
            <Button disabled={ready.length === 0 || paste.isPending} onClick={() => (decisions.length > 0 ? setStep('confirm') : void commit())}>
              {t('obligationUnits.create', { count: ready.length })}
            </Button>
          </ButtonBar>
        </div>
      ) : (
        <div data-paste-confirm="">
          <p className="mb-3">{t('obligationUnits.confirmBody')}</p>
          <div className="mb-4 max-h-[50vh] overflow-auto">
            <table className="w-full border-collapse text-meta">
              <thead>
                <tr>
                  <th className={cell}>{t('obligationUnits.columnReference')}</th>
                  <th className={cell}>{t('obligationUnits.columnTitle')}</th>
                  <th className={cell}>{t('obligationUnits.columnDecision')}</th>
                  <th className={cell}>{t('obligationUnits.columnReason')}</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((line) => (
                  <tr key={line.line}>
                    <td className={`${cell} font-mono`}>{line.reference}</td>
                    <td className={cell}>{line.title}</td>
                    <td className={cell}>{line.decision === null ? null : <PillRow pills={[presentApplicability(line.decision, t)]} />}</td>
                    <td className={cell}>{line.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {paste.isError ? <ProblemAlert error={paste.error} codes={problemCodes} /> : null}
          <ButtonBar>
            <Button variant="outline" onClick={() => setStep('dry')}>
              {t('common.cancel')}
            </Button>
            <Button disabled={paste.isPending} onClick={() => void commit()}>
              {t('obligationUnits.confirm', { count: decisions.length })}
            </Button>
          </ButtonBar>
        </div>
      )}
    </Modal>
  );
}
