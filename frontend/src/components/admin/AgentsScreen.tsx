'use client';

import Link from 'next/link';

import { useBankAgents } from '@/components/admin/admin-agents';
import { AgentBudgetPanel } from '@/components/admin/AgentBudgetPanel';
import { OurAgentsPanel } from '@/components/admin/OurAgentsPanel';
import { PlatformWatchPanel } from '@/components/admin/PlatformWatchPanel';
import { ResearchRequestList } from '@/components/admin/ResearchRequestList';
import { ResearchRequestPanel } from '@/components/admin/ResearchRequestPanel';
import { Notice } from '@/components/ui/Notice';
import { PageHead } from '@/components/ui/PageHead';
import { useTenant } from '@/features/tenant-admin/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { humanisePermission, usePermissions } from '@/shared/navigation/require-permission';

// /admin/agents (design/screens/admin-agents.html; AGT-03, AGT-04, AGT-05,
// ADM-01). The shell of the page and one mount point per panel. What bleqq
// watches is read under watch.read, which every member holds; everything a
// bank controls is drawn only for agents.manage, so a member without it sees
// bleqq's watch and one line saying what changing agents needs, never a
// page-level 403. The AI switch is the organisation's: this page says its
// state and links there, and never draws a second switch.

const MANAGE = 'agents.manage';

function AiLine() {
  const t = useT();
  const tenant = useTenant();
  if (!tenant.isSuccess) return null;
  const { aiEnabled, name } = tenant.data;
  return (
    <Notice tone={aiEnabled ? 'plain' : 'warn'} data-ai-enabled={aiEnabled}>
      {aiEnabled ? t('adminAgents.ai.on', { name }) : t('adminAgents.ai.off', { name })}{' '}
      <Link href="/admin/organisation" className="font-semibold underline">
        {t('adminAgents.ai.change')}
      </Link>
    </Notice>
  );
}

export function AgentsScreen() {
  const t = useT();
  const canManage = (usePermissions() ?? []).includes(MANAGE);
  const tenant = useTenant();
  const agents = useBankAgents(canManage);
  const own = agents.data?.items ?? [];

  return (
    <>
      <PageHead kicker={t('nav.admin')} title={t('adminAgents.title')} lede={t('adminAgents.lede')} />
      <AiLine />
      <PlatformWatchPanel />
      {canManage ? (
        <>
          <AgentBudgetPanel />
          {/* A request names one of our own agents, so the panel waits for the first one. */}
          {own.length > 0 ? (
            <>
              <ResearchRequestPanel agents={own} />
              <ResearchRequestList agents={own} />
            </>
          ) : null}
          <OurAgentsPanel agents={agents} aiEnabled={tenant.data?.aiEnabled ?? true} />
        </>
      ) : (
        <Notice data-agents-read-only="">{t('adminAgents.readOnly', { permission: humanisePermission(MANAGE) })}</Notice>
      )}
    </>
  );
}
