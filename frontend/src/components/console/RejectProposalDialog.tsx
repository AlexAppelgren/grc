'use client';

import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextArea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { ProblemAlert } from '@/components/ui/States';
import { useRejectProposal } from '@/features/proposals/hooks';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// "Reject with a reason" (design/screens/console-queue.html; PRO-01, PRO-S9).
// The reason is a `rejection_reason` library vocabulary row (chunk4-T2), read
// the same way every picker reads a vocabulary: the client stores and sends
// the key, never the label. `POST /proposals/{id}/reject` already refuses a
// call missing either the reason or the note with 422 `reason_required`
// (backend/apps/proposals/logic.py `reject`); the button mirrors that rule
// so the round trip only happens once both are given.

export function RejectProposalDialog({ proposalId, open, onClose }: { proposalId: string; open: boolean; onClose: () => void }) {
  const t = useT();
  const reasons = useVocabularyValues('rejection_reason');
  const reject = useRejectProposal(proposalId);
  const [reasonKey, setReasonKey] = useState('');
  const [note, setNote] = useState('');

  const close = () => {
    reject.reset();
    setReasonKey('');
    setNote('');
    onClose();
  };

  const canSubmit = reasonKey !== '' && note.trim() !== '';

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : close())} title={t('console.queue.rejectDialog.title')}>
      <Field id="reject-reason" label={t('console.queue.rejectDialog.reason')}>
        <Select id="reject-reason" value={reasonKey} onChange={(e) => setReasonKey(e.target.value)}>
          <option value="">{t('console.queue.rejectDialog.reasonPlaceholder')}</option>
          {(reasons.data ?? []).map((reason) => (
            <option key={reason.key} value={reason.key}>
              {reason.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field id="reject-note" label={t('console.queue.rejectDialog.note')} hint={t('console.queue.rejectDialog.hint')}>
        <TextArea id="reject-note" placeholder={t('console.queue.rejectDialog.notePlaceholder')} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {reject.isError ? <ProblemAlert error={reject.error} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={close} disabled={reject.isPending}>
          {t('common.cancel')}
        </Button>
        <Button
          variant="danger"
          disabled={!canSubmit || reject.isPending}
          onClick={() => reject.mutate({ rejectionCode: reasonKey, note: note.trim() }, { onSuccess: () => close() })}
        >
          {t('console.queue.rejectDialog.submit')}
        </Button>
      </ButtonBar>
    </Modal>
  );
}
