// The tenant-admin feature's names for the chunk 1 contract. Every shape is an
// alias over the generated schemas in src/types/api.generated.ts (from the
// backend's OpenAPI export; `bash generate-types.sh` regenerates them). A local
// definition remains only where the generator cannot express the shape, each
// with a one-line reason.

import type { UserSession } from '@/features/identity/types';
import type { components } from '@/types/api.generated';

type Schemas = components['schemas'];

export type { RoleRef } from '@/features/identity/types';

// Local: the generator emits one concrete page per item type (MembersPage, ApiKeysPage, ...), never a generic.
export interface Page<T> {
  items: T[];
  total: number;
}

// Partial: `limit` and `offset` have server defaults, which the generator renders as required fields.
export type PageQuery = Partial<Schemas['PageQuery']>;

export type OnboardingStep = Schemas['OnboardingStep'];
export type Tenant = Schemas['TenantOut'];
export type TenantUpdate = Schemas['TenantPatch'];

// Local: the backend types member status as a plain string; the fixed kind list lives here.
export type MemberStatus = 'invited' | 'active' | 'deactivated';

export type Member = Omit<Schemas['MemberOut'], 'status'> & { status: MemberStatus };
export type InviteBody = Schemas['MemberInvite'];
export type MemberUpdate = Schemas['MemberPatch'];

// Local: the backend types the invitation kind as a plain string; the fixed kind list lives here.
export type InvitationKind = 'invite' | 'reenrolment';

// Local: the backend types the server-computed invitation status as a plain string; the fixed kind list lives here.
export type InvitationStatus = 'pending' | 'accepted' | 'revoked' | 'expired';

export type Invitation = Omit<Schemas['InvitationOut'], 'kind' | 'status'> & { kind: InvitationKind; status: InvitationStatus };

export type MemberSession = UserSession;

export type TenantRole = Schemas['RoleOut'];
export type RoleCreate = Schemas['RoleCreate'];
export type RoleUpdate = Schemas['RolePatch'];
export type PermissionRef = Schemas['PermissionOut'];

/** A language row, as every vocabulary read returns it. */
export type LanguageRef = Schemas['RoleRef'];

export type ApiKey = Schemas['ApiKeyOut'];
/** `plainKey` is the only place the plain key ever appears. */
export type ApiKeyCreated = Schemas['ApiKeyCreated'];
export type ApiKeyCreate = Schemas['ApiKeyCreate'];

export type LoginEvent = Schemas['SecurityEventOut'];
