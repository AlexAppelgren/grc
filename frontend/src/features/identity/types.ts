// The identity feature's names for the chunk 1 contract. Every shape is an
// alias over the generated schemas in src/types/api.generated.ts (from the
// backend's OpenAPI export; `bash generate-types.sh` regenerates them). A local
// definition remains only where the generator cannot express the shape, each
// with a one-line reason.

import type { components } from '@/types/api.generated';
import type { CreationOptionsJson, RequestOptionsJson } from '@/shared/webauthn';

type Schemas = components['schemas'];

/** A vocabulary row as the API sends it: key and kind, and the label in the user's language. */
export type RoleRef = Schemas['RoleRef'];

export type MeUser = Schemas['MeUser'];
export type MeTenant = Schemas['MeTenant'];
export type Me = Schemas['Me'];
export type MeUpdate = Schemas['MePatch'];

// Local: the backend types the session kind as a plain string; the fixed kind list lives here.
export type SessionKind = 'enrolment' | 'full';

export type TokenResponse = Omit<Schemas['SessionTokens'], 'sessionKind'> & { sessionKind: SessionKind };

export type CodeRequestBody = Schemas['CodeRequestBody'];
export type CodeVerifyBody = Schemas['CodeVerifyBody'];
export type InvitationCodeVerifyBody = Schemas['InvitationCodeVerifyBody'];

// Local: the backend types the device type as a plain string; the fixed kind list (synced or device-bound) lives here.
export type PasskeyDeviceType = 'single_device' | 'multi_device';

export type Passkey = Omit<Schemas['PasskeyOut'], 'deviceType'> & { deviceType: PasskeyDeviceType };
export type PasskeyUpdate = Schemas['PasskeyPatch'];

// Local: src/shared/webauthn.ts owns the options JSON its parsers read (the generated ones allow null where the parsers do not).
export type PasskeyRegistrationOptions = CreationOptionsJson;
export type PasskeyRequestOptions = RequestOptionsJson;

export type RegisterVerifyBody = Schemas['PasskeyRegisterBody'];

/** `accessToken` is set when an enrolment session was upgraded to a full session; null when a full session added a passkey. */
export type RegisterVerifyResponse = Omit<Schemas['PasskeyRegistered'], 'passkey' | 'sessionKind'> & { passkey: Passkey; sessionKind: SessionKind };

export type AssertionVerifyBody = Schemas['PasskeyAssertBody'];
export type StepUpVerifyResponse = Schemas['StepUpResult'];
export type UserSession = Schemas['SessionOut'];
