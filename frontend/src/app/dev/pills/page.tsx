import { pillsOf } from '@/components/inventory/ObligationRow';
import { Pill, pillToneNames } from '@/components/ui/Pill';
import { PillRow } from '@/components/ui/PillRow';
import { presentCredential, presentEntry } from '@/features/agent-access/presentation';
import { presentDefinition, presentResearchRequest, presentRunState, presentTenantAgentState } from '@/features/agents/agents-presentation';
import { presentCaseStatus, presentOverdue, presentScanState } from '@/features/cases/case-presentation';
import { presentNotification } from '@/features/collab/collab-presentation';
import { presentResearch } from '@/features/footprint/footprint-presentation';
import { presentRoadmapItem, roadmapWhat } from '@/features/home/roadmap-presentation';
import { presentInstrument } from '@/features/library/instrument-presentation';
import { presentObligation, presentScope } from '@/features/library/obligation-presentation';
import { presentWorkItem } from '@/features/my-work/my-work-presentation';
import { presentContributorTeam, presentParticipant } from '@/features/participants/participants-presentation';
import { presentPrivateProposal } from '@/features/private-records/private-record-presentation';
import { presentApplicability, presentGap } from '@/features/register/register-presentation';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { presentSupportGrant } from '@/features/support-access/support-access-presentation';
import { presentChange } from '@/features/watch/change-presentation';
import { createT, defaultLocale, type Locale } from '@/shared/i18n';

import {
  accessEntries,
  actionsDue,
  agentRuns,
  applicabilities,
  caseStatuses,
  certificateDeadlines,
  changes,
  complianceStatuses,
  credentials,
  definitions,
  gapStatuses,
  gaps,
  instruments,
  notificationKinds,
  obligations,
  participants,
  privateObligation,
  privateProposals,
  registerEntries,
  researchRequests,
  roadmapItems,
  scanStates,
  scopeItemResearch,
  scopes,
  severities,
  supportGrants,
  tenantAgents,
  urgencies,
  workItems,
} from './samples';

// /dev/pills: every tone, every slot, every record type, light and dark side
// by side (playbook 6.7). A Playwright screenshot pins it in both themes.
// The columns carry their own theme class, so the page looks the same
// whichever theme the visitor uses.

function Record({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 rounded-card border border-line bg-surface px-4 py-3">{children}</div>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="microlabel mb-2.5 text-muted">{title}</h2>
      {children}
    </section>
  );
}

function Meta({ children }: { children: React.ReactNode }) {
  return <span className="text-meta text-muted">{children}</span>;
}

function ThemeColumn({ theme, locale }: { theme: 'light' | 'dark'; locale: Locale }) {
  const t = createT(locale);

  return (
    <div className={`${theme} bg-page px-6 pt-7 pb-10 text-fg`} data-theme-column={theme}>
      <h1 className="text-title">{theme === 'light' ? t('dev.pills.light') : t('dev.pills.dark')}</h1>
      <p className="mt-1 max-w-[60ch] text-meta text-muted">{t('dev.pills.lede')}</p>

      <Section title={t('dev.pills.tones')}>
        <span className="flex flex-wrap items-center gap-1.5">
          {pillToneNames.map((tone) => (
            <Pill key={tone} tone={tone}>
              {tone}
            </Pill>
          ))}
          <Pill tone="information" outlined>
            {t('dev.pills.tenantTag')}
          </Pill>
        </span>
      </Section>

      <Section title={t('dev.pills.changeRow')}>
        {changes.map((c) => (
          <Record key={c.title}>
            <PillRow pills={presentChange(c.facts, 'header')}>
              <Meta>{c.authority}</Meta>
            </PillRow>
            <h3 className="mt-1.5 font-semibold">{c.title}</h3>
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.obligationRow')}>
        {obligations.map((o) => (
          <Record key={o.title}>
            <PillRow pills={presentObligation(o.facts, 'row', t)} />
            <h3 className="mt-1.5 font-semibold">{o.title}</h3>
            {o.meta.length > 0 ? (
              <p className="mt-1 flex gap-4">
                {o.meta.map((m) => (
                  <Meta key={m}>{m}</Meta>
                ))}
              </p>
            ) : null}
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.obligationHeader')}>
        {obligations.map((o) => (
          <Record key={o.title}>
            <PillRow pills={presentObligation(o.facts, 'header', t)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.instrumentHeader')}>
        {instruments.map((i) => (
          <Record key={i.instrument.key}>
            <PillRow pills={presentInstrument(i, t)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.scopeBlock')}>
        <Record>
          {scopes.map((s, i) => {
            const scope = presentScope(s, t);
            return (
              <div key={s.dimension} className={i > 0 ? 'mt-1.5' : undefined}>
                {scope.plainText === undefined ? <PillRow pills={scope.pills} /> : <Meta>{scope.plainText}</Meta>}
              </div>
            );
          })}
        </Record>
      </Section>

      <Section title={t('dev.pills.gap')}>
        {gaps.map((g) => (
          <Record key={g.status.key}>
            <PillRow pills={presentGap(g)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.roadmapItem')}>
        <Record>
          {roadmapItems.map((item, i) => (
            <div key={i} className={i > 0 ? 'mt-1.5' : undefined}>
              <PillRow pills={presentRoadmapItem(item, t)} />
            </div>
          ))}
        </Record>
      </Section>

      <Section title={t('dev.pills.severityScales')}>
        <PillRow pills={urgencies.flatMap((u) => presentRoadmapItem({ urgency: u, ourDeadline: false }, t))} />
        <div className="mt-1.5">
          <PillRow
            pills={complianceStatuses.flatMap((c) =>
              presentObligation({ instrument: { key: 'x', label: 'x' }, binding: true, complianceStatus: c }, 'row', t).filter(
                (p) => p.key.startsWith('compliance:'),
              ),
            )}
          />
        </div>
        <div className="mt-1.5">
          <PillRow
            pills={gapStatuses.flatMap((g) =>
              presentGap({ status: g, severity: { key: 'low', kind: 'low', label: 'Low' } }).filter((p) => p.key.startsWith('gap-status:')),
            )}
          />
        </div>
        <div className="mt-1.5">
          <PillRow
            pills={severities.flatMap((s) =>
              presentGap({ status: { key: 'open', kind: 'open', label: 'Open' }, severity: s }).filter((p) => p.key.startsWith('severity:')),
            )}
          />
        </div>
      </Section>

      <Section title={t('dev.pills.registerEntry')}>
        {registerEntries.map((entry) => (
          <Record key={entry.instrument.key}>
            <PillRow pills={pillsOf(entry, t)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.applicability')}>
        <PillRow pills={applicabilities.map((answer) => presentApplicability(answer, t))} />
      </Section>

      <Section title={t('dev.pills.caseStatus')}>
        <PillRow pills={caseStatuses.map((status) => ({ ...presentCaseStatus(status, t), key: status.category }))} />
      </Section>

      <Section title={t('dev.pills.caseWork')}>
        <PillRow pills={scanStates.map((state) => presentScanState(state, t))} />
        <div className="mt-1.5">
          <PillRow pills={present(actionsDue.actions.map((action) => presentOverdue(action, actionsDue.today, t)))} />
        </div>
      </Section>

      <Section title={t('dev.pills.participants')}>
        <Record>
          {participants.rows.map((row) => (
            <div key={row.id} className="flex items-center gap-2">
              <span>{row.person?.name}</span>
              <PillRow pills={presentParticipant(row, participants.meId, t)} />
            </div>
          ))}
          <div className="mt-1.5">
            <PillRow pills={[presentContributorTeam(participants.team)]} />
          </div>
        </Record>
      </Section>

      <Section title={t('dev.pills.notificationKinds')}>
        <PillRow pills={notificationKinds.flatMap((kind) => presentNotification({ kind }, t).map((pill) => ({ ...pill, key: kind })))} />
      </Section>

      <Section title={t('dev.pills.myWork')}>
        {workItems.map((item, i) => (
          <Record key={i}>
            <PillRow pills={presentWorkItem(item)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.certificate')}>
        <Record>
          {certificateDeadlines.map((item, i) => (
            <div key={i} className={i > 0 ? 'mt-1.5' : undefined}>
              <PillRow pills={presentRoadmapItem(item, t)}>
                <Meta>{roadmapWhat(i === 0 ? 'certificate_expiry' : 'certificate_audit', t)}</Meta>
              </PillRow>
            </div>
          ))}
        </Record>
      </Section>

      <Section title={t('dev.pills.agents')}>
        <PillRow pills={tenantAgents.map((agent) => presentTenantAgentState(agent, t))} />
        <div className="mt-1.5">
          <PillRow pills={agentRuns.map((run) => presentRunState(run, t))} />
        </div>
        <div className="mt-1.5">
          <PillRow pills={researchRequests.map((request) => presentResearchRequest(request, t))} />
        </div>
        {definitions.map((definition) => (
          <div key={definition.id} className="mt-1.5">
            <PillRow pills={presentDefinition(definition, t)} />
          </div>
        ))}
      </Section>

      <Section title={t('dev.pills.agentAccess')}>
        {accessEntries.map(({ entry, orgReach }, i) => (
          <Record key={i}>
            <PillRow pills={presentEntry(entry, orgReach, t)} />
          </Record>
        ))}
        {credentials.keys.map((key) => (
          <Record key={key.id}>
            <PillRow pills={presentCredential(key, t, credentials.now)} />
          </Record>
        ))}
      </Section>

      <Section title={t('dev.pills.supportAccess')}>
        <PillRow pills={supportGrants.flatMap((grant) => presentSupportGrant(grant, t))} />
      </Section>

      <Section title={t('dev.pills.ownRecords')}>
        <Record>
          <PillRow pills={presentObligation(privateObligation, 'header', t)} />
        </Record>
        {privateProposals.map((proposal) => (
          <Record key={proposal.kind}>
            <PillRow pills={presentPrivateProposal(proposal, t)} />
          </Record>
        ))}
        <PillRow pills={present(scopeItemResearch.map((research) => presentResearch(research, t)))} />
      </Section>
    </div>
  );
}

/** The pills a function drew, leaving out the facts that draw none. */
function present(pills: readonly (PresentedPill | null)[]): PresentedPill[] {
  return pills.filter((pill): pill is PresentedPill => pill !== null);
}

export default function PillsGalleryPage() {
  return (
    <div className="grid min-h-screen md:grid-cols-2" data-pills-gallery="">
      <ThemeColumn theme="light" locale={defaultLocale} />
      <ThemeColumn theme="dark" locale={defaultLocale} />
    </div>
  );
}
