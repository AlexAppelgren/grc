import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  assertionToJson,
  createPasskey,
  fromBase64Url,
  getPasskey,
  isWebAuthnAvailable,
  parseCreationOptions,
  parseRequestOptions,
  registrationToJson,
  toBase64Url,
  webAuthnFailure,
} from './webauthn';

// The codecs and the shape mapping between the server's options_to_json
// object (py_webauthn, base64url strings) and the browser's ArrayBuffers,
// and back to the JSON the server verifies. No library (ADR 0003).

function bytes(...values: number[]): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(new ArrayBuffer(values.length));
  out.set(values);
  return out;
}

describe('base64url codecs', () => {
  it('round-trips bytes without padding and with the url alphabet', () => {
    const sample = bytes(251, 255, 191, 0, 1, 2, 62, 63);
    const text = toBase64Url(sample);
    expect(text).not.toMatch(/[+/=]/);
    expect(fromBase64Url(text)).toEqual(sample);
  });

  it('decodes standard base64 with padding as well', () => {
    expect(fromBase64Url('AQID')).toEqual(bytes(1, 2, 3));
    expect(fromBase64Url('AQI=')).toEqual(bytes(1, 2));
    expect(fromBase64Url('-_8')).toEqual(bytes(251, 255));
  });

  it('accepts an ArrayBuffer and an empty input', () => {
    expect(toBase64Url(new Uint8Array([]).buffer)).toBe('');
    expect(fromBase64Url('')).toEqual(bytes());
    expect(toBase64Url(bytes(104, 105).buffer)).toBe('aGk');
  });
});

const creationJson = {
  rp: { id: 'localhost', name: 'bleqq' },
  user: { id: 'dXNlci0x', name: 'anna@example-bank.test', displayName: 'Anna' },
  challenge: 'Y2hhbGxlbmdl',
  pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
  timeout: 120000,
  excludeCredentials: [{ type: 'public-key', id: 'AQID', transports: ['internal'] }],
  authenticatorSelection: { residentKey: 'required', userVerification: 'required' },
  attestation: 'none',
};

describe('parseCreationOptions', () => {
  it('decodes challenge, user id and excluded ids, keeps everything else', () => {
    const options = parseCreationOptions(creationJson);
    expect(new Uint8Array(options.challenge as ArrayBuffer)).toEqual(fromBase64Url('Y2hhbGxlbmdl'));
    expect(new Uint8Array(options.user.id as ArrayBuffer)).toEqual(fromBase64Url('dXNlci0x'));
    expect(options.user.name).toBe('anna@example-bank.test');
    expect(options.excludeCredentials?.map((c) => new Uint8Array(c.id as ArrayBuffer))).toEqual([bytes(1, 2, 3)]);
    expect(options.excludeCredentials?.[0]?.transports).toEqual(['internal']);
    expect(options.authenticatorSelection).toEqual({ residentKey: 'required', userVerification: 'required' });
    expect(options.attestation).toBe('none');
    expect(options.timeout).toBe(120000);
  });

  it('accepts the options wrapped in publicKey and no exclude list', () => {
    const { excludeCredentials: _dropped, ...rest } = creationJson;
    const options = parseCreationOptions({ publicKey: rest });
    expect(options.excludeCredentials).toEqual([]);
    expect(options.rp.id).toBe('localhost');
  });
});

describe('parseRequestOptions', () => {
  it('decodes the challenge and allowed ids; discoverable means an empty list', () => {
    const options = parseRequestOptions({ challenge: 'Y2g', rpId: 'localhost', userVerification: 'required', allowCredentials: [] });
    expect(new Uint8Array(options.challenge as ArrayBuffer)).toEqual(fromBase64Url('Y2g'));
    expect(options.allowCredentials).toEqual([]);
    expect(options.rpId).toBe('localhost');
    expect(options.userVerification).toBe('required');
  });

  it('keeps transports on allowed credentials and accepts the publicKey wrapper', () => {
    const options = parseRequestOptions({ publicKey: { challenge: 'Y2g', allowCredentials: [{ type: 'public-key', id: 'AQID', transports: ['usb'] }] } });
    expect(options.allowCredentials?.[0]?.transports).toEqual(['usb']);
    expect(new Uint8Array(options.allowCredentials?.[0]?.id as ArrayBuffer)).toEqual(bytes(1, 2, 3));
  });
});

function fakeRegistration(overrides: Partial<{ attachment: string | null; transports: string[] | undefined }> = {}) {
  const response = {
    clientDataJSON: bytes(1).buffer,
    attestationObject: bytes(2, 3).buffer,
    getTransports: overrides.transports === undefined ? undefined : () => overrides.transports,
  };
  return {
    id: 'AQID',
    rawId: bytes(1, 2, 3).buffer,
    type: 'public-key',
    authenticatorAttachment: overrides.attachment === undefined ? 'platform' : overrides.attachment,
    response,
    getClientExtensionResults: () => ({ credProps: { rk: true } }),
  };
}

function fakeAssertion(userHandle: ArrayBuffer | null) {
  return {
    id: 'AQID',
    rawId: bytes(1, 2, 3).buffer,
    type: 'public-key',
    authenticatorAttachment: 'cross-platform',
    response: {
      clientDataJSON: bytes(1).buffer,
      authenticatorData: bytes(4).buffer,
      signature: bytes(5, 6).buffer,
      userHandle,
    },
    getClientExtensionResults: () => ({}),
  };
}

describe('registrationToJson', () => {
  it('maps the credential to the JSON the server verifies', () => {
    const json = registrationToJson(fakeRegistration({ transports: ['internal', 'hybrid'] }) as unknown as PublicKeyCredential);
    expect(json).toEqual({
      id: 'AQID',
      rawId: 'AQID',
      type: 'public-key',
      authenticatorAttachment: 'platform',
      clientExtensionResults: { credProps: { rk: true } },
      response: { clientDataJSON: 'AQ', attestationObject: 'AgM', transports: ['internal', 'hybrid'] },
    });
  });

  it('omits transports when the browser cannot report them and attachment when unknown', () => {
    const json = registrationToJson(fakeRegistration({ attachment: null }) as unknown as PublicKeyCredential);
    expect(json.response.transports).toBeUndefined();
    expect(json.authenticatorAttachment).toBeUndefined();
  });
});

describe('assertionToJson', () => {
  it('maps the assertion with the user handle as base64url', () => {
    const json = assertionToJson(fakeAssertion(bytes(9).buffer) as unknown as PublicKeyCredential);
    expect(json).toEqual({
      id: 'AQID',
      rawId: 'AQID',
      type: 'public-key',
      authenticatorAttachment: 'cross-platform',
      clientExtensionResults: {},
      response: { clientDataJSON: 'AQ', authenticatorData: 'BA', signature: 'BQY', userHandle: 'CQ' },
    });
  });

  it('sends a null user handle when the authenticator returned none', () => {
    const json = assertionToJson(fakeAssertion(null) as unknown as PublicKeyCredential);
    expect(json.response.userHandle).toBeNull();
  });
});

describe('ceremonies through navigator.credentials', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('createPasskey passes decoded options and returns the JSON shape', async () => {
    const create = vi.fn(async (options: CredentialCreationOptions) => {
      expect(new Uint8Array(options.publicKey?.challenge as ArrayBuffer)).toEqual(fromBase64Url('Y2hhbGxlbmdl'));
      return fakeRegistration({ transports: ['internal'] });
    });
    vi.stubGlobal('navigator', { credentials: { create, get: vi.fn() } });
    const json = await createPasskey(creationJson);
    expect(create).toHaveBeenCalledOnce();
    expect(json.response.attestationObject).toBe('AgM');
  });

  it('getPasskey passes decoded options and returns the JSON shape', async () => {
    const get = vi.fn(async () => fakeAssertion(null));
    vi.stubGlobal('navigator', { credentials: { create: vi.fn(), get } });
    const json = await getPasskey({ challenge: 'Y2g', allowCredentials: [] });
    expect(get).toHaveBeenCalledOnce();
    expect(json.response.signature).toBe('BQY');
  });

  it('reports a cancelled or refused ceremony as a failure kind', async () => {
    vi.stubGlobal('navigator', { credentials: { create: vi.fn(async () => null), get: vi.fn() } });
    await expect(createPasskey(creationJson)).rejects.toMatchObject({ kind: 'cancelled' });
    vi.stubGlobal('navigator', {
      credentials: {
        create: vi.fn(async () => {
          throw new DOMException('user cancelled', 'NotAllowedError');
        }),
        get: vi.fn(async () => {
          throw new DOMException('excluded', 'InvalidStateError');
        }),
      },
    });
    await expect(createPasskey(creationJson)).rejects.toMatchObject({ kind: 'cancelled' });
    await expect(getPasskey({ challenge: 'Y2g' })).rejects.toMatchObject({ kind: 'already_registered' });
  });

  it('reports an unsupported browser', async () => {
    vi.stubGlobal('navigator', {});
    expect(isWebAuthnAvailable()).toBe(false);
    await expect(getPasskey({ challenge: 'Y2g' })).rejects.toMatchObject({ kind: 'unsupported' });
    vi.stubGlobal('navigator', { credentials: { create: vi.fn(), get: vi.fn() } });
    expect(isWebAuthnAvailable()).toBe(true);
  });

  it('classifies any other error as failed, keeping the message', () => {
    expect(webAuthnFailure(new Error('boom'))).toMatchObject({ kind: 'failed', message: 'boom' });
    expect(webAuthnFailure('x')).toMatchObject({ kind: 'failed' });
    expect(webAuthnFailure(new DOMException('no', 'SecurityError'))).toMatchObject({ kind: 'failed' });
    const failure = webAuthnFailure(new DOMException('no', 'NotAllowedError'));
    expect(webAuthnFailure(failure)).toBe(failure);
  });
});
