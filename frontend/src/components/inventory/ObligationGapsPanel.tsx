'use client';

import { useState } from 'react';

import { OneLine, Part } from '@/components/inventory/ObligationPanels';
import { GapForm } from '@/components/register/GapForm';
import { GapRecord, GapSummary } from '@/components/register/GapsScreen';
import { Button } from '@/components/ui/Button';
import { Row, Rows } from '@/components/ui/Panel';
import { QueryState } from '@/components/ui/States';
import { GAPS_EDIT, REGISTER_READ } from '@/features/register/gaps/gap-view';
import { useObligation } from '@/features/library/hooks';
import { OBLIGATION_GAPS_PAGE, useObligationGaps } from '@/features/register/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';

// "Gaps" on the obligation page (design/screens/tenant-obligation.html,
// gapsPanel(); REG-03): what is missing, each with its status, severity,
// owner and target date, opening its record in place, and Record a gap with
// this obligation fixed. A member whose roles do not read the register sees
// no panel, so the page asks nothing it would be refused.

function GapsPanelBody({ obligationId }: { obligationId: string }) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const gaps = useObligationGaps(obligationId, OBLIGATION_GAPS_PAGE);
  const obligation = useObligation(obligationId);
  const [open, setOpen] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const edits = permissions.includes(GAPS_EDIT);
  const items = gaps.data?.items ?? [];
  const title = obligation.data === undefined ? '' : (obligation.data.title?.text ?? obligation.data.instrument.shortName);

  const record = edits ? (
    <Button variant="ghost" size="small" onClick={() => setRecording(true)}>
      {t('obligationGaps.record')}
    </Button>
  ) : null;
  // No gap is one line with "Record a gap"; recorded gaps carry the heading and their count.
  const any = items.length > 0;

  return (
    <Part title={any ? `${t('obligationGaps.heading')} (${items.length})` : undefined} action={record} data-gaps-panel="">
      <QueryState query={gaps} rows={1} errorTitle={t('obligationGaps.errorTitle')}>
        {() =>
          any ? (
            <Rows>
              {items.map((gap) => (
                <Row key={gap.id} data-gap={gap.id} data-gap-status={gap.status.kind ?? undefined}>
                  <GapSummary gap={gap} withObligation={false} expanded={open === gap.id} onToggle={() => setOpen(open === gap.id ? null : gap.id)} />
                  {open === gap.id ? <GapRecord gap={gap} withObligation={false} wide={false} /> : null}
                </Row>
              ))}
            </Rows>
          ) : (
            <OneLine text={t('obligationGaps.none')} action={record} data-gaps-empty="" />
          )
        }
      </QueryState>
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
    </Part>
  );
}

export function ObligationGapsPanel({ obligationId }: { obligationId: string }) {
  const permissions = usePermissions() ?? [];
  return permissions.includes(REGISTER_READ) ? <GapsPanelBody obligationId={obligationId} /> : null;
}
