'use client';

import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, TextInput } from '@/components/ui/Field';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { describeDevice } from '@/features/identity/identity-presentation';
import { useDeactivateMember, useMembers, useMemberSessions, useReissueEnrolment, useRevokeMemberSessions, useRoles, useUpdateMember } from '@/features/tenant-admin/hooks';
import { presentMember } from '@/features/tenant-admin/members-presentation';
import type { Member } from '@/features/tenant-admin/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// One member (design/screens/admin-members.html, detail): roles and title,
// sessions, re-issue enrolment, deactivate. Role changes, re-issue and
// deactivation go through the api client's step-up prompt where the server
// asks for it; 409 last_admin renders in place. Another tenant's member id
// answers 404 and renders Not found, never Restricted (playbook 4.4).

function sameKeys(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && [...a].sort().every((key, i) => key === [...b].sort()[i]);
}

// The mutation lives in the parent: a saved role change re-keys this form, and a
// remount would otherwise drop the mutation's success and the "Saved." line with it.
function RolesForm({ member, update }: { member: Member; update: ReturnType<typeof useUpdateMember> }) {
  const t = useT();
  const roles = useRoles();
  const initialKeys = member.roles.map((role) => role.key);
  const [title, setTitle] = useState(member.title);
  const [roleKeys, setRoleKeys] = useState<string[]>(initialKeys);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body = { title: title.trim(), ...(sameKeys(roleKeys, initialKeys) ? {} : { roleKeys }) };
    update.mutate({ userId: member.userId, body });
  };

  return (
    <form onSubmit={submit} noValidate aria-busy={update.isPending}>
      <Panel title={t('admin.members.rolesAndTitle')}>
        <Field id="member-title" label={t('admin.members.titleField')}>
          <TextInput id="member-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <CheckGroup legend={t('admin.members.roles')} hint={t('admin.members.rolesStepUp')}>
          {roles.isPending ? <StatusLine>{t('common.loading')}</StatusLine> : null}
          {(roles.data ?? [])
            .filter((role) => role.active || roleKeys.includes(role.key))
            .map((role) => (
              <CheckRow
                key={role.key}
                id={`member-role-${role.key}`}
                label={role.label}
                checked={roleKeys.includes(role.key)}
                onChange={(checked) => setRoleKeys((current) => (checked ? [...current, role.key] : current.filter((k) => k !== role.key)))}
              />
            ))}
        </CheckGroup>
        {update.isError ? <ProblemAlert error={update.error} codes={{ last_admin: t('admin.members.lastAdmin'), step_up_required: t('problem.stepUpCancelled') }} /> : null}
        {update.isSuccess ? <StatusLine tone="positive">{t('admin.members.saved')}</StatusLine> : null}
        <ButtonBar>
          <Button type="submit" disabled={update.isPending}>
            {t('common.save')}
          </Button>
        </ButtonBar>
      </Panel>
    </form>
  );
}

function ConfirmedAction({
  label,
  confirmText,
  doneText,
  codes,
  pending,
  error,
  done,
  onConfirm,
}: {
  label: string;
  confirmText: string;
  doneText: string;
  codes?: Readonly<Record<string, string>>;
  pending: boolean;
  error: unknown;
  done: boolean;
  onConfirm: () => void;
}) {
  const t = useT();
  const [confirming, setConfirming] = useState(false);
  return (
    <>
      {error !== null && error !== undefined ? <ProblemAlert error={error} codes={codes} /> : null}
      {done ? <StatusLine tone="positive">{doneText}</StatusLine> : null}
      {confirming ? <StatusLine>{confirmText}</StatusLine> : null}
      <ButtonBar>
        {confirming ? (
          <>
            <Button variant="ghost" size="small" onClick={() => setConfirming(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="danger"
              size="small"
              disabled={pending}
              onClick={() => {
                setConfirming(false);
                onConfirm();
              }}
            >
              {label}
            </Button>
          </>
        ) : (
          <Button variant="danger" size="small" disabled={pending} onClick={() => setConfirming(true)}>
            {label}
          </Button>
        )}
      </ButtonBar>
    </>
  );
}

export function MemberDetailScreen({ userId }: { userId: string }) {
  const t = useT();
  const ctx = useFormatContext();
  const router = useRouter();
  const members = useMembers();
  const sessions = useMemberSessions(userId);
  const update = useUpdateMember();
  const revokeAll = useRevokeMemberSessions();
  const reissue = useReissueEnrolment();
  const deactivate = useDeactivateMember();

  const member = members.data?.items.find((m) => m.userId === userId);
  const notFound = (sessions.isError && problemStatus(sessions.error) === 404) || (members.isSuccess && member === undefined && !sessions.isPending);

  if (notFound) return <NotFoundScreen body={t('admin.members.notFoundBody')} backHref="/admin/members" backLabel={t('admin.members.backToMembers')} />;
  if (members.isPending || member === undefined) {
    if (members.isError) return <ErrorState title={t('admin.members.errorTitle')} onRetry={() => void members.refetch()} />;
    return <LoadingState rows={3} />;
  }

  const stepUpCodes = { step_up_required: t('problem.stepUpCancelled') };

  return (
    <>
      <BackLink href="/admin/members" label={t('admin.members.backToMembers')} />
      <PageHead title={member.name} />
      <div className="mb-4">
        <PillRow pills={presentMember(member, t)} />
      </div>

      <Panel title={t('admin.members.profile')}>
        <dl className="m-0 grid gap-x-3.5 gap-y-2.5 text-meta md:grid-cols-[150px_1fr]">
          <dt className="text-muted">{t('admin.members.emailLabel')}</dt>
          <dd className="m-0">{member.email}</dd>
          <dt className="text-muted">{t('admin.members.lastSeenLabel')}</dt>
          <dd className="m-0">{member.lastSeenAt === null ? t('common.never') : formatDateTime(member.lastSeenAt, ctx)}</dd>
          <dt className="text-muted">{t('admin.members.passkeysLabel')}</dt>
          <dd className="m-0">{member.passkeyCount}</dd>
          <dt className="text-muted">{t('admin.members.sessionsLabel')}</dt>
          <dd className="m-0">{member.activeSessions}</dd>
        </dl>
      </Panel>

      {/* Keyed on the saved roles, so a saved change becomes the new baseline without an effect. */}
      <RolesForm key={`${member.userId}:${member.roles.map((r) => r.key).join(',')}:${member.title}`} member={member} update={update} />

      <Panel title={t('admin.members.sessionsPanel')}>
        {sessions.isPending ? (
          <LoadingState rows={1} />
        ) : sessions.isError ? (
          <ProblemAlert error={sessions.error} />
        ) : sessions.data.length === 0 ? (
          <p className="text-muted">{t('admin.members.noSessions')}</p>
        ) : (
          <Rows>
            {sessions.data.map((session) => (
              <Row key={session.id}>
                <h3 className="mb-1 font-semibold">{describeDevice(session.userAgent, t)}</h3>
                <Meta>
                  <span>{t('me.sessions.signedIn', { date: formatDateTime(session.createdAt, ctx) })}</span>
                  <span>{t('me.sessions.lastSeen', { date: formatDateTime(session.lastSeenAt, ctx) })}</span>
                </Meta>
              </Row>
            ))}
          </Rows>
        )}
        <ConfirmedAction
          label={t('admin.members.revokeAll')}
          confirmText={t('admin.members.revokeAllConfirm')}
          doneText={t('admin.members.sessionsRevoked')}
          pending={revokeAll.isPending}
          error={revokeAll.error}
          done={revokeAll.isSuccess}
          onConfirm={() => revokeAll.mutate(userId)}
        />
      </Panel>

      <Panel title={t('admin.members.passkeysPanel')}>
        <p className="text-muted">{t('admin.members.reissueLede')}</p>
        <ConfirmedAction
          label={t('admin.members.reissue')}
          confirmText={t('admin.members.reissueConfirm')}
          doneText={t('admin.members.reissued')}
          codes={stepUpCodes}
          pending={reissue.isPending}
          error={reissue.error}
          done={reissue.isSuccess}
          onConfirm={() => reissue.mutate(userId)}
        />
      </Panel>

      <Panel title={t('admin.members.access')}>
        <p className="text-muted">{t('admin.members.deactivateLede')}</p>
        <ConfirmedAction
          label={t('admin.members.deactivate')}
          confirmText={t('admin.members.deactivateConfirm')}
          doneText={t('admin.members.deactivatedDone')}
          codes={{ last_admin: t('admin.members.lastAdmin'), ...stepUpCodes }}
          pending={deactivate.isPending}
          error={deactivate.error}
          done={deactivate.isSuccess}
          onConfirm={() => deactivate.mutate(userId, { onSuccess: () => router.push('/admin/members') })}
        />
      </Panel>
    </>
  );
}
