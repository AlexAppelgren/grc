'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';

import { bankAgentKeys, parseCap, refusals, spendOf, useBankBudget } from '@/components/admin/admin-agents';
import { Button } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { Notice } from '@/components/ui/Notice';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { formatEuro } from '@/features/agents/agents-presentation';
import { putAgentBudget } from '@/features/agents/api';
import type { AgentBudget } from '@/features/agents/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// Spend this month (admin-agents.html sections 1 and 5; AGT-04, ruling 3):
// one monthly cap for the bank, the month's spend on our own agents against
// it, and the line saying bleqq's watch runs at bleqq's cost, so the figure is
// not misread. Without a cap there is no meter, never an empty one. A cap at or
// below the spend is accepted and pauses our agents, so the list is re-read.

function CapForm({ budget }: { budget: AgentBudget }) {
  const t = useT();
  const queryClient = useQueryClient();
  const [value, setValue] = useState(budget.monthlyCap ?? '');
  const [invalid, setInvalid] = useState(false);
  const save = useMutation({
    mutationFn: (monthlyCap: string) => putAgentBudget({ monthlyCap }),
    onSuccess: async (saved) => {
      queryClient.setQueryData(bankAgentKeys.budget, saved);
      await queryClient.invalidateQueries({ queryKey: bankAgentKeys.list });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const cap = parseCap(String(value));
    setInvalid(cap === null);
    if (cap !== null) save.mutate(cap);
  };

  return (
    <form onSubmit={submit} noValidate aria-busy={save.isPending} className="mt-3 flex flex-wrap items-end gap-3" data-cap-form="">
      <div className="min-w-[200px] grow">
        <Field id="agent-cap" label={t('adminAgents.budget.capLabel')} error={invalid ? t('adminAgents.budget.capInvalid') : undefined}>
          <TextInput id="agent-cap" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} aria-invalid={invalid || undefined} />
        </Field>
      </div>
      <Button type="submit" className="mb-3" disabled={save.isPending}>
        {t('adminAgents.budget.setCap')}
      </Button>
      {save.isError ? <ProblemAlert className="w-full text-meta text-negative" error={save.error} codes={refusals(t)} /> : null}
      {save.isSuccess ? (
        <p role="status" className="w-full text-meta text-positive">
          {t('adminAgents.budget.saved')}
        </p>
      ) : null}
    </form>
  );
}

export function AgentBudgetPanel() {
  const t = useT();
  const ctx = useFormatContext();
  const budget = useBankBudget(true);

  return (
    <Panel title={t('adminAgents.budget.title')} data-agent-budget="">
      {budget.isPending ? (
        <LoadingState rows={1} />
      ) : budget.isError ? (
        <ErrorState title={t('adminAgents.budget.errorTitle')} onRetry={() => void budget.refetch()} />
      ) : (
        <BudgetBody budget={budget.data} format={(amount) => formatEuro(amount, ctx) ?? amount} />
      )}
    </Panel>
  );
}

function BudgetBody({ budget, format }: { budget: AgentBudget; format: (amount: string) => string }) {
  const t = useT();
  const spend = spendOf(budget);
  const spent = format(budget.spentThisMonth);

  return (
    <>
      {spend.reached ? <Notice tone="warn">{t('adminAgents.budget.reached')}</Notice> : null}
      <p className="text-title tabular-nums" data-spend="">
        {budget.monthlyCap === null ? t('adminAgents.budget.noCap', { spent }) : t('adminAgents.budget.ofCap', { spent, cap: format(budget.monthlyCap) })}
      </p>
      {spend.percent === null ? null : (
        <div
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={spend.percent}
          aria-label={t('adminAgents.budget.meter', { percent: spend.percent })}
          className="my-2 h-2 overflow-hidden rounded-[3px] bg-neutral-soft"
        >
          <i className="block h-full bg-brand" style={{ width: `${spend.percent}%` }} />
        </div>
      )}
      <p className="text-meta text-muted">{t('adminAgents.budget.bleqqLine')}</p>
      <p className="text-meta text-muted">{t('adminAgents.budget.whenReached')}</p>
      <CapForm budget={budget} />
    </>
  );
}
