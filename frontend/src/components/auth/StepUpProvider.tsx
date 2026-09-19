'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { ProblemAlert, StatusLine } from '@/components/ui/States';
import { useStepUp } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { setStepUpHandler } from '@/shared/utils/api-client';

// The step-up prompt (design/screens/auth-step-up.html, playbook 4.2). The
// api client calls `request()` on a 403 step_up_required; the promise
// resolves true after a fresh assertion is stored, false when the person
// cancels, and the client retries or gives up accordingly. Concurrent
// requests share one prompt.

type Resolver = (confirmed: boolean) => void;

const StepUpContext = createContext<() => Promise<boolean>>(() => Promise.resolve(false));

export function useRequestStepUp(): () => Promise<boolean> {
  return useContext(StepUpContext);
}

export function StepUpProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const stepUp = useStepUp();
  const resolvers = useRef<Resolver[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const request = useCallback(
    () =>
      new Promise<boolean>((resolve) => {
        resolvers.current.push(resolve);
        setError(null);
        setOpen(true);
      }),
    [],
  );

  useEffect(() => {
    setStepUpHandler(request);
    return () => setStepUpHandler(null);
  }, [request]);

  const finish = useCallback((confirmed: boolean) => {
    const waiting = resolvers.current;
    resolvers.current = [];
    setOpen(false);
    setError(null);
    for (const resolve of waiting) resolve(confirmed);
  }, []);

  const confirm = async () => {
    setError(null);
    try {
      await stepUp.mutateAsync();
      finish(true);
    } catch (failure) {
      setError(failure);
    }
  };

  return (
    <StepUpContext.Provider value={request}>
      {children}
      <Modal
        open={open}
        onOpenChange={(next) => {
          if (!next && !stepUp.isPending) finish(false);
        }}
        title={t('stepUp.title')}
        description={t('stepUp.body')}
      >
        {stepUp.isPending ? <StatusLine>{t('stepUp.waiting')}</StatusLine> : null}
        {error !== null ? <ProblemAlert error={error} codes={{}} className="mt-2.5 text-meta text-negative" /> : null}
        {error !== null ? <p className="mt-1 text-meta text-muted">{t('stepUp.refused')}</p> : null}
        <ButtonBar>
          <Button variant="outline" onClick={() => finish(false)} disabled={stepUp.isPending}>
            {t('stepUp.cancel')}
          </Button>
          <Button onClick={() => void confirm()} disabled={stepUp.isPending}>
            {t('stepUp.use')}
          </Button>
        </ButtonBar>
      </Modal>
    </StepUpContext.Provider>
  );
}
