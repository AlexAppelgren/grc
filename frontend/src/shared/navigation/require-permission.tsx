'use client';

import { isAxiosError } from 'axios';
import { Component, createContext, useContext, type ErrorInfo, type ReactNode } from 'react';

import { useT } from '@/shared/i18n/LocaleProvider';
import { unlocks } from '@/shared/navigation/registry';

// The client gate (playbook 6.2). `permissions` is the signed-in user's
// permission list; `null` means no session is known yet. The gate is UX
// hinting: the server's structured 403 is the enforcer, and the same
// Restricted screen renders that 403 through the error boundary below.

interface PermissionsContextValue {
  permissions: readonly string[] | null;
}

const PermissionsContext = createContext<PermissionsContextValue>({ permissions: null });

export function PermissionsProvider({
  permissions,
  children,
}: {
  permissions: readonly string[] | null;
  children: ReactNode;
}) {
  return <PermissionsContext.Provider value={{ permissions }}>{children}</PermissionsContext.Provider>;
}

export function usePermissions(): readonly string[] | null {
  return useContext(PermissionsContext).permissions;
}

/** The server's structured 403 body (playbook 4.4). */
export interface Forbidden {
  detail: string;
  code: string;
  requiredPermission?: string;
}

export function forbiddenFrom(error: unknown): Forbidden | null {
  if (!isAxiosError(error) || error.response?.status !== 403) return null;
  const body: unknown = error.response.data;
  if (typeof body !== 'object' || body === null) return { detail: '', code: 'forbidden' };
  const record = body as Record<string, unknown>;
  return {
    detail: typeof record.detail === 'string' ? record.detail : '',
    code: typeof record.code === 'string' ? record.code : 'forbidden',
    requiredPermission: typeof record.requiredPermission === 'string' ? record.requiredPermission : undefined,
  };
}

// `cases.signoff` reads "cases signoff": the grant name, not a role name.
export function humanisePermission(permission: string): string {
  return permission.replace(/[._]/g, ' ');
}

export function RestrictedScreen({ detail, code, requiredPermission }: Partial<Forbidden>) {
  const t = useT();
  return (
    <section role="alert" className="mx-auto max-w-[60ch] py-16 text-center">
      <h1>{t('restricted.title')}</h1>
      <p className="mt-3 text-muted">{detail && detail.length > 0 ? detail : t('restricted.body')}</p>
      {requiredPermission !== undefined ? (
        <p className="mt-3 text-meta text-muted">{t('restricted.needs', { permission: humanisePermission(requiredPermission) })}</p>
      ) : null}
      {code !== undefined ? (
        <p className="mt-1 font-mono text-meta text-muted">{t('restricted.reference', { code })}</p>
      ) : null}
    </section>
  );
}

interface BoundaryState {
  forbidden: Forbidden | null;
  other: Error | null;
}

class ForbiddenBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  override state: BoundaryState = { forbidden: null, other: null };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    const forbidden = forbiddenFrom(error);
    if (forbidden !== null) return { forbidden, other: null };
    return { forbidden: null, other: error instanceof Error ? error : new Error(String(error)) };
  }

  override componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Anything that is not a 403 is rethrown in render for the route's own
    // error boundary; nothing is logged here because the error may carry
    // tenant content.
  }

  override render(): ReactNode {
    if (this.state.other !== null) throw this.state.other;
    if (this.state.forbidden !== null) return <RestrictedScreen {...this.state.forbidden} />;
    return this.props.children;
  }
}

export function RequirePermission({ anyOf, children }: { anyOf: readonly string[]; children: ReactNode }) {
  const permissions = usePermissions();
  if (!unlocks(anyOf, permissions ?? [])) {
    return <RestrictedScreen requiredPermission={anyOf[0]} />;
  }
  return <ForbiddenBoundary>{children}</ForbiddenBoundary>;
}
