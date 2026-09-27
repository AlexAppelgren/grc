'use client';

import Link from 'next/link';

import { EmptyState } from '@/components/ui/EmptyState';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { definitionName, presentDefinition } from '@/features/agents/agents-presentation';
import { useAgentDefinitions } from '@/features/agents/hooks';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDate } from '@/shared/utils/format';

// Agent definitions (design/screens/console-agent-definitions.html, AGT-03,
// ADM-02): every agent bleqq ships, whether bleqq runs it for every bank or a
// bank adds it as its own, and the version it runs. A definition opens on its
// versions, and a platform one on its settings and runs. Nothing here names a
// bank or carries a bank's figure, and no prompt body is ever a screen.

export function AgentDefinitionsScreen() {
  const t = useT();
  const ctx = useFormatContext();
  const definitions = useAgentDefinitions();

  return (
    <>
      <PageHead title={t('console.agents.title')} lede={t('console.agents.lede')} />
      {definitions.isPending ? (
        <LoadingState rows={4} />
      ) : definitions.isError ? (
        <ErrorState title={t('console.agents.errorTitle')} onRetry={() => void definitions.refetch()} />
      ) : definitions.data.items.length === 0 ? (
        <EmptyState title={t('console.agents.emptyTitle')} body={t('console.agents.emptyBody')} />
      ) : (
        <Rows data-agent-definitions="">
          {definitions.data.items.map((definition) => (
            <Row key={definition.id} data-agent-definition={definition.key}>
              <PillRow pills={presentDefinition(definition, t)} />
              <h3 className="mt-2 mb-1 font-semibold">
                <Link href={`/console/agents/${encodeURIComponent(definition.key)}`} className="underline-offset-2 hover:underline">
                  {definitionName(definition.key)}
                </Link>
              </h3>
              <p className="text-muted">{definition.description}</p>
              <Meta>
                <code className="font-mono">{definition.key}</code>
                <span>{definition.publishedAt === null ? t('console.agents.notPublished') : t('console.agents.published', { date: formatDate(definition.publishedAt, ctx) })}</span>
              </Meta>
            </Row>
          ))}
        </Rows>
      )}
    </>
  );
}
