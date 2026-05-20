/**
 * TrapRoyalties — WebAuthn client
 * Handles FaceID / TouchID / Windows Hello registration and authentication.
 */

// ── Base64url helpers ─────────────────────────────────────────────────────────
function b64decode(str) {
  str = str.replace(/-/g, '+').replace(/_/g, '/');
  while (str.length % 4) str += '=';
  const bin = atob(str);
  return Uint8Array.from(bin, c => c.charCodeAt(0));
}

function b64encode(buf) {
  const bytes = new Uint8Array(buf);
  let str = '';
  for (const b of bytes) str += String.fromCharCode(b);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

// ── Prepare credential for server ────────────────────────────────────────────
function prepCredential(cred) {
  const r = cred.response;
  const out = {
    id:    cred.id,
    rawId: b64encode(cred.rawId),
    type:  cred.type,
    response: {
      clientDataJSON: b64encode(r.clientDataJSON),
    },
  };

  // Registration
  if (r.attestationObject) {
    out.response.attestationObject = b64encode(r.attestationObject);
  }

  // Authentication
  if (r.authenticatorData) {
    out.response.authenticatorData = b64encode(r.authenticatorData);
    out.response.signature         = b64encode(r.signature);
    if (r.userHandle) {
      out.response.userHandle = b64encode(r.userHandle);
    }
  }

  return out;
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function setStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className   = 'status ' + (type || '');
}

// ── Registration ──────────────────────────────────────────────────────────────
async function registerBiometric(auditId) {
  const btn = document.getElementById('bio-btn');
  btn.disabled = true;
  setStatus('Requesting registration options...');

  try {
    // 1. Get options from server
    const res  = await fetch('/webauthn/register-options', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ audit_id: auditId }),
    });
    const opts = await res.json();
    if (opts.error) throw new Error(opts.error);

    // 2. Decode binary fields
    opts.challenge = b64decode(opts.challenge);
    opts.user.id   = b64decode(opts.user.id);
    if (opts.excludeCredentials) {
      opts.excludeCredentials = opts.excludeCredentials.map(c => ({
        ...c, id: b64decode(c.id),
      }));
    }

    // 3. Prompt biometric
    setStatus('Waiting for FaceID / TouchID...');
    const cred = await navigator.credentials.create({ publicKey: opts });

    // 4. Verify with server
    setStatus('Verifying with server...');
    const vRes   = await fetch('/webauthn/register-verify', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(prepCredential(cred)),
    });
    const result = await vRes.json();
    if (!result.ok) throw new Error(result.error || 'Verification failed');

    setStatus('Biometric registered! Preparing your download...', 'success');
    setTimeout(() => {
      window.location.href = `/download/${result.audit_id}/${result.token}`;
    }, 1200);

  } catch (err) {
    console.error(err);
    const msg = err.name === 'NotAllowedError'
      ? 'Biometric prompt was cancelled. Please try again.'
      : 'Error: ' + err.message;
    setStatus(msg, 'error');
    btn.disabled = false;
  }
}

// ── Authentication ─────────────────────────────────────────────────────────────
async function authBiometric(auditId) {
  const btn = document.getElementById('bio-btn');
  btn.disabled = true;
  setStatus('Requesting authentication...');

  try {
    // 1. Get options
    const res  = await fetch('/webauthn/auth-options', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ audit_id: auditId }),
    });
    const opts = await res.json();
    if (opts.error) throw new Error(opts.error);

    // 2. Decode binary fields
    opts.challenge = b64decode(opts.challenge);
    if (opts.allowCredentials) {
      opts.allowCredentials = opts.allowCredentials.map(c => ({
        ...c, id: b64decode(c.id),
      }));
    }

    // 3. Prompt biometric
    setStatus('Waiting for FaceID / TouchID...');
    const cred = await navigator.credentials.get({ publicKey: opts });

    // 4. Verify with server
    setStatus('Verifying identity...');
    const vRes   = await fetch('/webauthn/auth-verify', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(prepCredential(cred)),
    });
    const result = await vRes.json();
    if (!result.ok) throw new Error(result.error || 'Authentication failed');

    setStatus('Identity verified! Downloading your report...', 'success');
    setTimeout(() => {
      window.location.href = `/download/${result.audit_id}/${result.token}`;
    }, 800);

  } catch (err) {
    console.error(err);
    const msg = err.name === 'NotAllowedError'
      ? 'Biometric prompt was cancelled. Please try again.'
      : 'Error: ' + err.message;
    setStatus(msg, 'error');
    btn.disabled = false;
  }
}
