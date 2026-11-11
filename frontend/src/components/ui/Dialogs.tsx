'use client';

import type { FormEvent, ReactNode } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { ProblemAlert } from '@/components/ui/States';
import { useT } from '@/shared/i18n/LocaleProvider';

// The two dialogs every screen asks for (playbook 6.8, prototype `.modal`):
// a form that ends in Cancel and its submit, and a question that ends in
// Cancel and its action. Escape, a click outside and Cancel all close; a
// refused write shows above the buttons through ProblemAlert, with the
// screen's own sentences for the codes it knows.

type DataAttributes = { [name: `data-${string}`]: string | undefined };

export function FormDialog({
  title,
  description,
  submitLabel,
  pending,
  error,
  codes,
  submitDisabled = false,
  danger = false,
  onSubmit,
  onClose,
  formProps,
  children,
}: {
  title: string;
  description?: string;
  submitLabel: string;
  pending: boolean;
  /** The write's error, shown above the buttons; leave it out when the fields show it themselves. */
  error?: unknown;
  codes?: Readonly<Record<string, string>>;
  submitDisabled?: boolean;
  danger?: boolean;
  onSubmit: () => void;
  onClose: () => void;
  formProps?: DataAttributes;
  children: ReactNode;
}) {
  const t = useT();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    // The dialog is portalled, but React still bubbles its submit to a form it opens from.
    event.stopPropagation();
    onSubmit();
  };
  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={title} description={description}>
      <form onSubmit={submit} noValidate aria-busy={pending} {...formProps}>
        {children}
        {error === undefined ? null : <ProblemAlert error={error} codes={codes} />}
        <ButtonBar>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant={danger ? 'danger' : 'primary'} disabled={pending || submitDisabled}>
            {submitLabel}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function ConfirmDialog({
  title,
  body,
  action,
  cancelLabel,
  busy,
  error,
  codes,
  danger = false,
  onConfirm,
  onClose,
  children,
}: {
  title: string;
  body?: string;
  action: string;
  /** The way back, where the question words it its own way ("Keep it"). */
  cancelLabel?: string;
  busy: boolean;
  error?: unknown;
  codes?: Readonly<Record<string, string>>;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  children?: ReactNode;
}) {
  const t = useT();
  return (
    <Modal open onOpenChange={(open) => (open ? undefined : onClose())} title={title} description={body}>
      {children}
      {error === undefined ? null : <ProblemAlert error={error} codes={codes} />}
      <ButtonBar>
        <Button variant="outline" disabled={busy} onClick={onClose}>
          {cancelLabel ?? t('common.cancel')}
        </Button>
        <Button variant={danger ? 'danger' : 'primary'} disabled={busy} onClick={onConfirm}>
          {action}
        </Button>
      </ButtonBar>
    </Modal>
  );
}
