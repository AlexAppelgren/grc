'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckGroup, CheckRow, Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useFormatContext } from '@/features/identity/hooks';
import { useInvitations, useInviteMember, useMembers, useResendInvitation, useRevokeInvitation, useRoles } from '@/features/tenant-admin/hooks';
import { presentInvitation, presentMember } from '@/features/tenant-admin/members-presentation';
import type { Invitation, Member } from '@/features/tenant-admin/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';

// Members and invitations (design/screens/admin-members.html; ID-01, ADM-01).
// Role pills are labelled from the tenant's role rows; the invite form's
// options come from GET /tenant/roles, never from existing memberships.

type Tab = 'members' | 'invitations';

function MemberRow({ member }: { member: Member }) {
  const t = useT();
  const ctx = useFormatContext();
  return (
    <Link href={`/admin/members/${member.userId}`} className="block rounded-card border border-line bg-surface px-4 py-3 no-underline hover:hover-fill" data-member-id={member.userId}>
      <h3 className="mb-1 font-semibold">{member.name}</h3>
      <div className="mb-1.5">
        <PillRow pills={presentMember(member, t)} />
      </div>
      <Meta>
        <span>{member.email}</span>
        {member.title.length > 0 ? <span>{member.title}</span> : null}
        <span>{member.lastSeenAt === null ? t('admin.members.neverSignedIn') : t('admin.members.lastSeen', { date: formatDateTime(member.lastSeenAt, ctx) })}</span>
        <span>{t('admin.members.passkeys', { count: member.passkeyCount })}</span>
        <span>{t('admin.members.sessions', { count: member.activeSessions })}</span>
      </Meta>
    </Link>
  );
}

function InvitationRow({ invitation }: { invitation: Invitation }) {
  const t = useT();
  const ctx = useFormatContext();
  const resend = useResendInvitation();
  const revoke = useRevokeInvitation();
  const open = invitation.status === 'pending';
  return (
    <Row data-invitation-id={invitation.id}>
      <h3 className="mb-1 font-semibold">{invitation.email}</h3>
      <div className="mb-1.5">
        <PillRow pills={presentInvitation(invitation, t)} />
      </div>
      <Meta>
        {invitation.title.length > 0 ? <span>{invitation.title}</span> : null}
        <span>{t('admin.members.invited', { date: formatDateTime(invitation.createdAt, ctx) })}</span>
        <span>{t('admin.members.expires', { date: formatDateTime(invitation.expiresAt, ctx) })}</span>
      </Meta>
      {resend.isError ? <ProblemAlert error={resend.error} /> : null}
      {revoke.isError ? <ProblemAlert error={revoke.error} /> : null}
      {resend.isSuccess ? <StatusLine tone="positive">{t('admin.members.resent')}</StatusLine> : null}
      {open ? (
        <ButtonBar>
          <Button variant="outline" size="small" disabled={revoke.isPending} onClick={() => revoke.mutate(invitation.id)}>
            {t('admin.members.revoke')}
          </Button>
          <Button size="small" disabled={resend.isPending} onClick={() => resend.mutate(invitation.id)}>
            {t('admin.members.resend')}
          </Button>
        </ButtonBar>
      ) : null}
    </Row>
  );
}

function InviteModal({ open, onClose, onSent }: { open: boolean; onClose: () => void; onSent: (email: string) => void }) {
  const t = useT();
  const roles = useRoles();
  const invite = useInviteMember();
  const [email, setEmail] = useState('');
  const [title, setTitle] = useState('');
  const [roleKeys, setRoleKeys] = useState<string[]>([]);
  const [problem, setProblem] = useState<'email' | 'roles' | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (email.trim() === '') {
      setProblem('email');
      return;
    }
    if (roleKeys.length === 0) {
      setProblem('roles');
      return;
    }
    setProblem(null);
    invite.mutate(
      { email: email.trim(), roleKeys, title: title.trim() },
      {
        onSuccess: () => {
          onSent(email.trim());
          setEmail('');
          setTitle('');
          setRoleKeys([]);
          onClose();
        },
      },
    );
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={t('admin.members.inviteTitle')}>
      <form onSubmit={submit} noValidate aria-busy={invite.isPending}>
        <Field id="invite-email" label={t('admin.members.email')} error={problem === 'email' ? t('admin.members.emailRequired') : undefined}>
          <TextInput id="invite-email" type="email" autoComplete="off" placeholder={t('admin.members.emailPlaceholder')} value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field id="invite-title" label={t('admin.members.titleField')} hint={t('admin.members.titleHint')}>
          <TextInput id="invite-title" placeholder={t('admin.members.titlePlaceholder')} value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <CheckGroup legend={t('admin.members.roles')} error={problem === 'roles' ? t('admin.members.rolesRequired') : undefined}>
          {roles.isPending ? <StatusLine>{t('common.loading')}</StatusLine> : null}
          {roles.isError ? <ProblemAlert error={roles.error} /> : null}
          {(roles.data ?? [])
            .filter((role) => role.active)
            .map((role) => (
              <CheckRow
                key={role.key}
                id={`invite-role-${role.key}`}
                label={role.label}
                hint={role.usageNote.length > 0 ? role.usageNote : undefined}
                checked={roleKeys.includes(role.key)}
                onChange={(checked) => setRoleKeys((current) => (checked ? [...current, role.key] : current.filter((k) => k !== role.key)))}
              />
            ))}
        </CheckGroup>
        {invite.isError ? <ProblemAlert error={invite.error} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={invite.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={invite.isPending}>
            {t('admin.members.send')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function MembersScreen() {
  const t = useT();
  const members = useMembers();
  const invitations = useInvitations();
  const [tab, setTab] = useState<Tab>('members');
  const [inviting, setInviting] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

  return (
    <>
      <BackLink href="/admin" label={t('admin.back')} />
      <PageHead title={t('admin.members.title')} actions={<Button onClick={() => setInviting(true)}>{t('admin.members.invite')}</Button>} />
      {sentTo !== null ? <StatusLine tone="positive">{t('admin.members.invitationSent', { email: sentTo })}</StatusLine> : null}
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
        {(['members', 'invitations'] as const).map((key) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            className={tab === key ? 'border-b-2 border-fg px-3 py-2.5 font-semibold whitespace-nowrap' : 'border-b-2 border-transparent px-3 py-2.5 font-medium whitespace-nowrap text-muted'}
            onClick={() => setTab(key)}
          >
            {key === 'members' ? t('admin.members.tabMembers') : t('admin.members.tabInvitations')}
          </button>
        ))}
      </div>
      {tab === 'members' ? (
        members.isPending ? (
          <LoadingState rows={3} />
        ) : members.isError ? (
          <ErrorState title={t('admin.members.errorTitle')} onRetry={() => void members.refetch()} />
        ) : members.data.items.length === 0 ? (
          <EmptyState title={t('admin.members.emptyTitle')} body={t('admin.members.emptyBody')} />
        ) : (
          <Rows data-members-list="">
            {members.data.items.map((member) => (
              <MemberRow key={member.userId} member={member} />
            ))}
          </Rows>
        )
      ) : invitations.isPending ? (
        <LoadingState />
      ) : invitations.isError ? (
        <ErrorState title={t('admin.members.errorTitle')} onRetry={() => void invitations.refetch()} />
      ) : invitations.data.items.length === 0 ? (
        <EmptyState title={t('admin.members.noInvitationsTitle')} body={t('admin.members.noInvitationsBody')} />
      ) : (
        <Rows data-invitations-list="">
          {invitations.data.items.map((invitation) => (
            <InvitationRow key={invitation.id} invitation={invitation} />
          ))}
        </Rows>
      )}
      <InviteModal open={inviting} onClose={() => setInviting(false)} onSent={setSentTo} />
    </>
  );
}
