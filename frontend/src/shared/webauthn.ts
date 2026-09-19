// WebAuthn in the browser through navigator.credentials, no library (ADR
// 0003). The server (py_webauthn 3.0.0, `options_to_json`) sends the
// PublicKeyCredential*Options with `challenge`, `user.id`,
// `excludeCredentials[].id` and `allowCredentials[].id` as base64url strings
// at the top level; a `publicKey` wrapper is accepted as well. The browser
// wants ArrayBuffers, and answers with ArrayBuffers that go back to the
// server as the standard PublicKeyCredential-to-JSON shape (base64url).
// Verified against the py_webauthn source on 2026-09-19 (Verification_Log).

export function toBase64Url(input: ArrayBuffer | Uint8Array): string {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function fromBase64Url(text: string): Uint8Array<ArrayBuffer> {
  const standard = text.replace(/-/g, '+').replace(/_/g, '/');
  const padded = standard + '='.repeat((4 - (standard.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** A bytes field as the server sends it. */
type B64 = string;

interface DescriptorJson {
  type: string;
  id: B64;
  transports?: string[];
}

export interface CreationOptionsJson {
  rp: { id?: string; name: string };
  user: { id: B64; name: string; displayName: string };
  challenge: B64;
  pubKeyCredParams: { type: string; alg: number }[];
  timeout?: number;
  excludeCredentials?: DescriptorJson[];
  authenticatorSelection?: {
    authenticatorAttachment?: string;
    residentKey?: string;
    requireResidentKey?: boolean;
    userVerification?: string;
  };
  attestation?: string;
  hints?: string[];
  extensions?: Record<string, unknown>;
}

export interface RequestOptionsJson {
  challenge: B64;
  timeout?: number;
  rpId?: string;
  allowCredentials?: DescriptorJson[];
  userVerification?: string;
  extensions?: Record<string, unknown>;
}

type MaybeWrapped<T extends object> = T | { publicKey: T };

function unwrap<T extends object>(options: MaybeWrapped<T>): T {
  return 'publicKey' in options ? (options as { publicKey: T }).publicKey : (options as T);
}

function descriptor(json: DescriptorJson): PublicKeyCredentialDescriptor {
  return {
    type: json.type as PublicKeyCredentialType,
    id: fromBase64Url(json.id),
    transports: json.transports as AuthenticatorTransport[] | undefined,
  };
}

export function parseCreationOptions(options: MaybeWrapped<CreationOptionsJson>): PublicKeyCredentialCreationOptions {
  const json = unwrap(options);
  return {
    rp: json.rp,
    user: { ...json.user, id: fromBase64Url(json.user.id) },
    challenge: fromBase64Url(json.challenge),
    pubKeyCredParams: json.pubKeyCredParams as PublicKeyCredentialParameters[],
    timeout: json.timeout,
    excludeCredentials: (json.excludeCredentials ?? []).map(descriptor),
    authenticatorSelection: json.authenticatorSelection as AuthenticatorSelectionCriteria | undefined,
    attestation: json.attestation as AttestationConveyancePreference | undefined,
    extensions: json.extensions as AuthenticationExtensionsClientInputs | undefined,
  };
}

export function parseRequestOptions(options: MaybeWrapped<RequestOptionsJson>): PublicKeyCredentialRequestOptions {
  const json = unwrap(options);
  return {
    challenge: fromBase64Url(json.challenge),
    timeout: json.timeout,
    rpId: json.rpId,
    allowCredentials: (json.allowCredentials ?? []).map(descriptor),
    userVerification: json.userVerification as UserVerificationRequirement | undefined,
    extensions: json.extensions as AuthenticationExtensionsClientInputs | undefined,
  };
}

/** The registration credential as the server's `parse_registration_credential_json` reads it. */
export interface RegistrationCredentialJson {
  id: string;
  rawId: B64;
  type: string;
  authenticatorAttachment?: string;
  clientExtensionResults: Record<string, unknown>;
  response: { clientDataJSON: B64; attestationObject: B64; transports?: string[] };
}

/** The assertion as the server's `parse_authentication_credential_json` reads it. */
export interface AssertionCredentialJson {
  id: string;
  rawId: B64;
  type: string;
  authenticatorAttachment?: string;
  clientExtensionResults: Record<string, unknown>;
  response: { clientDataJSON: B64; authenticatorData: B64; signature: B64; userHandle: B64 | null };
}

type AttestationWithTransports = AuthenticatorAttestationResponse & { getTransports?: () => string[] };

function attachmentOf(credential: PublicKeyCredential): string | undefined {
  const attachment = (credential as { authenticatorAttachment?: string | null }).authenticatorAttachment;
  return attachment === null || attachment === undefined ? undefined : attachment;
}

export function registrationToJson(credential: PublicKeyCredential): RegistrationCredentialJson {
  const response = credential.response as AttestationWithTransports;
  const transports = typeof response.getTransports === 'function' ? response.getTransports() : undefined;
  return {
    id: credential.id,
    rawId: toBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: attachmentOf(credential),
    clientExtensionResults: credential.getClientExtensionResults() as Record<string, unknown>,
    response: {
      clientDataJSON: toBase64Url(response.clientDataJSON),
      attestationObject: toBase64Url(response.attestationObject),
      ...(transports === undefined ? {} : { transports }),
    },
  };
}

export function assertionToJson(credential: PublicKeyCredential): AssertionCredentialJson {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: attachmentOf(credential),
    clientExtensionResults: credential.getClientExtensionResults() as Record<string, unknown>,
    response: {
      clientDataJSON: toBase64Url(response.clientDataJSON),
      authenticatorData: toBase64Url(response.authenticatorData),
      signature: toBase64Url(response.signature),
      userHandle: response.userHandle === null ? null : toBase64Url(response.userHandle),
    },
  };
}

// Why a ceremony did not produce a credential. Screens branch on `kind`
// (never on a browser message) to pick their copy.
export type WebAuthnFailureKind = 'cancelled' | 'already_registered' | 'unsupported' | 'failed';

export class WebAuthnFailure extends Error {
  readonly kind: WebAuthnFailureKind;
  constructor(kind: WebAuthnFailureKind, message: string) {
    super(message);
    this.name = 'WebAuthnFailure';
    this.kind = kind;
  }
}

export function webAuthnFailure(error: unknown): WebAuthnFailure {
  if (error instanceof WebAuthnFailure) return error;
  if (error instanceof DOMException) {
    // NotAllowedError: the person cancelled or the prompt timed out.
    // InvalidStateError: the authenticator already holds an excluded credential.
    if (error.name === 'NotAllowedError') return new WebAuthnFailure('cancelled', error.message);
    if (error.name === 'InvalidStateError') return new WebAuthnFailure('already_registered', error.message);
    return new WebAuthnFailure('failed', error.message);
  }
  return new WebAuthnFailure('failed', error instanceof Error ? error.message : String(error));
}

export function isWebAuthnAvailable(): boolean {
  return typeof navigator !== 'undefined' && navigator.credentials !== undefined && typeof navigator.credentials.create === 'function';
}

async function run<T>(ceremony: () => Promise<Credential | null>, toJson: (credential: PublicKeyCredential) => T): Promise<T> {
  if (!isWebAuthnAvailable()) throw new WebAuthnFailure('unsupported', 'navigator.credentials is not available');
  let credential: Credential | null;
  try {
    credential = await ceremony();
  } catch (error) {
    throw webAuthnFailure(error);
  }
  if (credential === null) throw new WebAuthnFailure('cancelled', 'no credential returned');
  return toJson(credential as PublicKeyCredential);
}

/** Runs the registration ceremony and returns the JSON for `register/verify`. */
export function createPasskey(options: MaybeWrapped<CreationOptionsJson>): Promise<RegistrationCredentialJson> {
  return run(() => navigator.credentials.create({ publicKey: parseCreationOptions(options) }), registrationToJson);
}

/** Runs the assertion ceremony (sign-in or step-up) and returns the JSON for the matching verify route. */
export function getPasskey(options: MaybeWrapped<RequestOptionsJson>): Promise<AssertionCredentialJson> {
  return run(() => navigator.credentials.get({ publicKey: parseRequestOptions(options) }), assertionToJson);
}
