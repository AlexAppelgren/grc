'use client';

import { useState } from 'react';

import { GapForm } from '@/components/register/GapForm';
import { GapRecord, GapSummary } from '@/components/register/GapsScreen';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { GAPS_EDIT, REGISTER_READ } from '@/features/gaps/gap-view';
import { useObligation } from '@/features/library/hooks';
import { useObligationGaps, useRegisterEntry } from '@/features/register/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';

// "Gaps" on the obligation page (design/screens/tenant-obligation.html,
// gapsPanel(); REG-03): what is missing, each with its status, severity,
// owner and target date, opening its record in place, and Record a gap with
// this obligation fixed. A member whose roles do not read the register sees
// no panel, so the page asks nothing it would be refused.

const ALL = { limit: 100 } as const;
// The compliance categories that say something is missing.
const SHORTFALL = ['gap', 'partly'];

function GapsPanelBody({ obligationId }: { obligationId: string }) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const gaps = useObligationGaps(obligationId, ALL);
  const entry = useRegisterEntry(obligationId);
  const obligation = useObligation(obligationId);
  const [open, setOpen] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const edits = permissions.includes(GAPS_EDIT);
  const items = gaps.data?.items ?? [];
  const shortfall = items.length === 0 && SHORTFALL.includes(entry.data?.complianceStatus.kind ?? '');
  const title = obligation.data === undefined ? '' : (obligation.data.title?.text ?? obligation.data.instrument.shortName);

  return (
    <Panel title={t('obligationGaps.heading')} data-gaps-panel="">
      {gaps.isPending ? (
        <LoadingState rows={1} />
      ) : gaps.isError ? (
        <ErrorState title={t('obligationGaps.errorTitle')} onRetry={() => void gaps.refetch()} />
      ) : items.length === 0 ? (
        <p className="text-meta text-muted" data-gaps-empty="">
          {t(shortfall ? 'obligationGaps.statusSaysGap' : 'obligationGaps.none')}
        </p>
      ) : (
        <Rows>
          {items.map((gap) => (
            <Row key={gap.id} data-gap={gap.id} data-gap-status={gap.status.kind ?? undefined}>
              <GapSummary gap={gap} withObligation={false} expanded={open === gap.id} onToggle={() => setOpen(open === gap.id ? null : gap.id)} />
              {open === gap.id ? <GapRecord gap={gap} withObligation={false} wide={false} /> : null}
            </Row>
          ))}
        </Rows>
      )}
      {edits ? (
        <ButtonBar>
          <Button variant={shortfall ? 'primary' : 'ghost'} size="small" onClick={() => setRecording(true)}>
            {t('obligationGaps.record')}
          </Button>
        </ButtonBar>
      ) : null}
      {recording ? (
        <GapForm
          obligationId={obligationId}
          obligationTitle={title}
          gap={null}
          onClose={() => setRecording(false)}
          onDone={(saved) => {
            setRecording(false);
            setOpen(saved.id);
          }}
        />
      ) : null}
    </Panel>
  );
}

export function ObligationGapsPanel({ obligationId }: { obligationId: string }) {
  const permissions = usePermissions() ?? [];
  return permissions.includes(REGISTER_READ) ? <GapsPanelBody obligationId={obligationId} /> : null;
}
