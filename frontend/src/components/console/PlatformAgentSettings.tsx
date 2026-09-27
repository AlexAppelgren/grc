'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, Select, TextInput } from '@/components/ui/Field';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { CADENCE_KEY } from '@/features/agents/agents-presentation';
import { usePlatformAgentSettings, useUpdatePlatformAgentSettings } from '@/features/agents/hooks';
import type { AgentCadence, PlatformAgentSettings } from '@/features/agents/types';
import { useJurisdictions } from '@/features/footprint/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// How one of bleqq's own agents runs (console-agent-definitions.html, section
// 5): its cadence, the jurisdictions it sweeps and its monthly budget. These
// are the same for every bank, so the panel says so in plain words, and the
// save asks for a passkey (the api client drives it off `step_up_required`)
// and is audited with before and after by the server.

const CADENCES = Object.keys(CADENCE_KEY) as AgentCadence[];

/** Euro with at most two decimals, the shape the API takes; empty means no budget. */
const EURO = /^\d{1,8}(\.\d{1,2})?$/;

function SettingsForm({ agentKey, name, saved }: { agentKey: string; name: string; saved: PlatformAgentSettings }) {
  const t = useT();
  const update = useUpdatePlatformAgentSettings(agentKey);
  const jurisdictions = useJurisdictions();
  const [cadence, setCadence] = useState<AgentCadence>(saved.cadence);
  const [chosen, setChosen] = useState<string[]>(saved.jurisdictions);
  const [budget, setBudget] = useState(saved.monthlyBudget ?? '');
  const [problem, setProblem] = useState<'jurisdictions' | 'budget' | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  // A saved key the reference list no longer holds stays choosable, so a save never drops it silently.
  const listed = jurisdictions.data ?? [];
  const options = [...listed, ...saved.jurisdictions.filter((key) => !listed.some((j) => j.key === key)).map((key) => ({ key, label: key }))];

  const reset = () => {
    setCadence(saved.cadence);
    setChosen(saved.jurisdictions);
    setBudget(saved.monthlyBudget ?? '');
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
      { cadence, jurisdictions: chosen, monthlyBudget: amount === '' ? null : amount },
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
          hint={t('console.agents.settings.budgetHint')}
          error={problem === 'budget' ? t('console.agents.settings.budgetInvalid') : undefined}
        >
          <TextInput id="platform-agent-budget" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} />
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
      {settings.isPending ? (
        <LoadingState rows={2} />
      ) : settings.isError ? (
        <ErrorState title={t('console.agents.settings.errorTitle')} onRetry={() => void settings.refetch()} />
      ) : (
        <SettingsForm agentKey={agentKey} name={name} saved={settings.data} />
      )}
    </Panel>
  );
}
