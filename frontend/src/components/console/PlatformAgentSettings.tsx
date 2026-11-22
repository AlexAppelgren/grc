'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, Select, TextInput } from '@/components/ui/Field';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { ProblemAlert, QueryState, StatusLine } from '@/components/ui/States';
import { CADENCE_KEY } from '@/features/agents/agents-presentation';
import { usePlatformAgentSettings, useUpdatePlatformAgentSettings } from '@/features/agents/hooks';
import type { AgentCadence, PlatformAgentSettings } from '@/features/agents/types';
import { useJurisdictions } from '@/features/footprint/hooks';
import type { MessageKey } from '@/shared/i18n';
import { useT } from '@/shared/i18n/LocaleProvider';

// How one of bleqq's own agents runs (console-agent-definitions.html, section
// 5): its cadence, the jurisdictions it sweeps, its monthly budget, and the
// model and effort its calls use (D-148), empty meaning the platform's. These
// are the same for every bank, so the panel says so in plain words, and the
// save asks for a passkey (the api client drives it off `step_up_required`)
// and is audited with before and after by the server.

const CADENCES = Object.keys(CADENCE_KEY) as AgentCadence[];

type AgentEffort = NonNullable<PlatformAgentSettings['effort']>;
type AgentModel = NonNullable<PlatformAgentSettings['model']>;

// The effort levels in the order they are offered, each with its label (D-148).
const EFFORT_KEY: Record<AgentEffort, MessageKey> = {
  low: 'console.agents.settings.effort.low',
  medium: 'console.agents.settings.effort.medium',
  high: 'console.agents.settings.effort.high',
  xhigh: 'console.agents.settings.effort.xhigh',
  max: 'console.agents.settings.effort.max',
};
const EFFORTS = Object.keys(EFFORT_KEY) as AgentEffort[];

/** Euro with at most two decimals, the shape the API takes; empty means no budget. */
const EURO = /^\d{1,8}(\.\d{1,2})?$/;

function SettingsForm({ agentKey, name, saved }: { agentKey: string; name: string; saved: PlatformAgentSettings }) {
  const t = useT();
  const update = useUpdatePlatformAgentSettings(agentKey);
  const jurisdictions = useJurisdictions();
  const [cadence, setCadence] = useState<AgentCadence>(saved.cadence);
  const [chosen, setChosen] = useState<string[]>(saved.jurisdictions);
  const [budget, setBudget] = useState(saved.monthlyBudget ?? '');
  const [model, setModel] = useState<AgentModel | ''>(saved.model ?? '');
  const [effort, setEffort] = useState<AgentEffort | ''>(saved.effort ?? '');
  const [problem, setProblem] = useState<'jurisdictions' | 'budget' | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  // A saved key the reference list no longer holds stays choosable, so a save never drops it silently.
  const listed = jurisdictions.data ?? [];
  const options = [...listed, ...saved.jurisdictions.filter((key) => !listed.some((j) => j.key === key)).map((key) => ({ key, label: key }))];

  const reset = () => {
    setCadence(saved.cadence);
    setChosen(saved.jurisdictions);
    setBudget(saved.monthlyBudget ?? '');
    setModel(saved.model ?? '');
    setEffort(saved.effort ?? '');
    setProblem(null);
    update.reset();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setStatus(null);
    if (chosen.length === 0) return setProblem('jurisdictions');
    const amount = budget.trim();
    if (amount !== '' && !EURO.test(amount)) return setProblem('budget');
    setProblem(null);
    update.mutate(
      { cadence, jurisdictions: chosen, monthlyBudget: amount === '' ? null : amount, model: model === '' ? null : model, effort: effort === '' ? null : effort },
      { onSuccess: () => setStatus(t('console.agents.settings.saved', { name })) },
    );
  };

  return (
    <form onSubmit={submit} noValidate aria-busy={update.isPending} data-platform-settings-form="">
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field id="platform-agent-cadence" label={t('console.agents.settings.cadence')}>
          <Select id="platform-agent-cadence" value={cadence} onChange={(e) => setCadence(e.target.value as AgentCadence)}>
            {CADENCES.map((key) => (
              <option key={key} value={key}>
                {t(CADENCE_KEY[key])}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          id="platform-agent-budget"
          label={t('console.agents.settings.budget')}
          hint={t('console.agents.settings.budgetHint', { amount: saved.defaultMonthlyBudget })}
          error={problem === 'budget' ? t('console.agents.settings.budgetInvalid') : undefined}
        >
          <TextInput id="platform-agent-budget" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} />
        </Field>
        <Field id="platform-agent-model" label={t('console.agents.settings.model')} hint={t('console.agents.settings.modelHint')}>
          <Select id="platform-agent-model" value={model} onChange={(e) => setModel(e.target.value as AgentModel | '')}>
            <option value="">{t('console.agents.settings.modelDefault', { model: saved.defaultModel })}</option>
            {saved.models.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="platform-agent-effort" label={t('console.agents.settings.effort')} hint={t('console.agents.settings.effortHint')}>
          <Select id="platform-agent-effort" value={effort} onChange={(e) => setEffort(e.target.value as AgentEffort | '')}>
            <option value="">{t('console.agents.settings.effortDefault', { effort: t(EFFORT_KEY[saved.defaultEffort]) })}</option>
            {EFFORTS.map((key) => (
              <option key={key} value={key}>
                {t(EFFORT_KEY[key])}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <CheckGroup legend={t('console.agents.settings.jurisdictions')} error={problem === 'jurisdictions' ? t('console.agents.settings.jurisdictionsRequired') : undefined}>
        {options.map((jurisdiction) => (
          <CheckRow
            key={jurisdiction.key}
            id={`platform-agent-jurisdiction-${jurisdiction.key}`}
            label={jurisdiction.label}
            checked={chosen.includes(jurisdiction.key)}
            onChange={(checked) => setChosen((current) => (checked ? [...current, jurisdiction.key] : current.filter((key) => key !== jurisdiction.key)))}
          />
        ))}
      </CheckGroup>
      {jurisdictions.isError ? <ProblemAlert error={jurisdictions.error} /> : null}
      {update.isError ? <ProblemAlert error={update.error} codes={{ step_up_required: t('problem.stepUpCancelled') }} /> : null}
      {status === null ? null : <StatusLine tone="positive">{status}</StatusLine>}
      <p className="mt-3 text-meta text-muted">{t('console.agents.settings.saveNote')}</p>
      <ButtonBar>
        <Button variant="outline" onClick={reset} disabled={update.isPending}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={update.isPending}>
          {t('console.agents.settings.save')}
        </Button>
      </ButtonBar>
    </form>
  );
}

export function PlatformAgentSettingsPanel({ agentKey, name }: { agentKey: string; name: string }) {
  const t = useT();
  const settings = usePlatformAgentSettings(agentKey);

  return (
    <Panel title={t('console.agents.settings.title')} data-platform-settings="">
      <Notice tone="warn">{t('console.agents.settings.everyBank')}</Notice>
      <QueryState query={settings} rows={2} errorTitle={t('console.agents.settings.errorTitle')}>
        {(data) => (
          <SettingsForm agentKey={agentKey} name={name} saved={data} />
        )}
      </QueryState>
    </Panel>
  );
}
