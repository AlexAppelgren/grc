'use client';

import { BackLink } from '@/components/admin/AdminGate';
import { SessionPolicyPanel } from '@/components/admin/SessionPolicyPanel';
import { TenantReachPanel } from '@/components/admin/TenantReachPanel';
import { PageHead } from '@/components/ui/PageHead';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useSecurityPolicy } from '@/features/security-policy/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// Security (design/screens/admin-security.html, ID-08, ADM-01), for a holder of
// security.manage. The card's passkey policy (ID-07) is out of R2 (D-100), so
// the page holds the session limits and the mount point for tenant reach; the
// IP allow-list and single sign-on arrive with their own cards.
export function SecurityPolicyScreen() {
  const t = useT();
  const policy = useSecurityPolicy();
  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.security.title')} lede={t('admin.security.lede')} />
      {policy.isPending ? (
        <LoadingState />
      ) : policy.isError ? (
        <ErrorState title={t('admin.security.errorTitle')} onRetry={() => void policy.refetch()} />
      ) : (
        <>
          <SessionPolicyPanel policy={policy.data} />
          <TenantReachPanel />
        </>
      )}
    </>
  );
}
