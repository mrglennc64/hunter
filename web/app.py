"""
TrapRoyalties Checkout & Biometric Unlock Portal

Routes:
  GET  /checkout/<audit_id>          Redacted preview + $150 CTA
  POST /pay/<audit_id>               Create Stripe Checkout session
  GET  /payment-success              Stripe callback → biometric gate
  GET  /biometric/<audit_id>         WebAuthn register (first) or auth (return)
  POST /webauthn/register-options    Generate registration challenge
  POST /webauthn/register-verify     Verify + store credential
  POST /webauthn/auth-options        Generate auth challenge
  POST /webauthn/auth-verify         Verify assertion → issue download token
  GET  /download/<audit_id>/<token>  Serve PDF (one-time token)

Env vars (.env):
  STRIPE_SECRET_KEY   sk_live_...
  FLASK_SECRET        random string (auto-generated if missing)
  RP_ID               your domain (e.g. traproyalties.com) — localhost for dev
  ORIGIN              https://traproyalties.com — http://localhost:5000 for dev
  WEBAUTHN_ENABLED    true/false (default false until you have HTTPS + domain)
"""

import os, sys, json, secrets, hashlib, datetime, threading, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from monad import anchor_scan, anchor_pdf

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, send_file, session, abort,
)
import stripe
from dotenv import load_dotenv

load_dotenv()

# ── WebAuthn (optional — requires HTTPS + real domain in prod) ────────────────
try:
    from webauthn import (
        generate_registration_options, verify_registration_response,
        generate_authentication_options, verify_authentication_response,
        options_to_json,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        AuthenticatorAttachment,
        UserVerificationRequirement,
        ResidentKeyRequirement,
        PublicKeyCredentialDescriptor,
    )
    from webauthn.helpers.cose import COSEAlgorithmIdentifier
    _WA_LIB = True
except ImportError:
    _WA_LIB = False

# ── Config ────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(32))

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
CATALOG     = os.path.join(DATA_DIR, "unlock_catalog.json")
PAID_DB     = os.path.join(DATA_DIR, "paid.json")
PREVIEW_DB  = os.path.join(DATA_DIR, "preview.json")
PDFS_DIR    = os.path.join(DATA_DIR, "pdfs")
EVENTS_DB   = os.path.join(DATA_DIR, "email_events.json")

# Minimal 1×1 transparent GIF — no external dependency needed
_PIXEL_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
    b'\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00'
    b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
)

RP_ID       = os.getenv("RP_ID",    "localhost")
RP_NAME     = "TrapRoyalties Forensic Unit"
ORIGIN      = os.getenv("ORIGIN",   "http://localhost:5000")
WA_ENABLED  = os.getenv("WEBAUTHN_ENABLED", "false").lower() == "true"
PRICE_CENTS = 15000  # $150.00


# ── Storage helpers ───────────────────────────────────────────────────────────
def _load(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)

def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_lead(audit_id):
    return _load(CATALOG).get(audit_id)

def is_paid(audit_id):
    return _load(PAID_DB).get(audit_id, {}).get("paid", False)

def mark_paid(audit_id, stripe_session_id):
    db = _load(PAID_DB)
    db.setdefault(audit_id, {}).update({
        "paid": True,
        "stripe_session": stripe_session_id,
        "paid_at": datetime.datetime.utcnow().isoformat(),
    })
    _save(PAID_DB, db)

def store_credential(audit_id, cred_dict):
    db = _load(PAID_DB)
    db.setdefault(audit_id, {})["credential"] = cred_dict
    _save(PAID_DB, db)

def get_credential(audit_id):
    return _load(PAID_DB).get(audit_id, {}).get("credential")

def issue_download_token(audit_id):
    token = secrets.token_urlsafe(32)
    db = _load(PAID_DB)
    db.setdefault(audit_id, {})["download_token"] = token
    _save(PAID_DB, db)
    return token

def mark_artist_scanned(audit_id):
    """Record that artist completed face scan. Returns the SHA-256 anchor."""
    sha = hashlib.sha256(f"SCAN-{audit_id}-{datetime.datetime.utcnow().isoformat()}".encode()).hexdigest()
    db = _load(PREVIEW_DB)
    db[audit_id] = {
        "scanned_at": datetime.datetime.utcnow().isoformat(),
        "sha256": sha,
    }
    _save(PREVIEW_DB, db)
    # Anchor on Monad in background (non-blocking)
    lead = get_lead(audit_id)
    if lead:
        def _anchor():
            result = anchor_scan(audit_id, lead.get("artist",""), lead.get("track",""), sha)
            if "tx" in result:
                db2 = _load(PREVIEW_DB)
                if audit_id in db2:
                    db2[audit_id]["monad_tx"] = result["tx"]
                    db2[audit_id]["monad_block"] = result["block"]
                    _save(PREVIEW_DB, db2)
        threading.Thread(target=_anchor, daemon=True).start()
    return sha

def get_scan_entry(audit_id):
    return _load(PREVIEW_DB).get(audit_id)


# ── Email event tracking ───────────────────────────────────────────────────────
_events_lock = threading.Lock()

def log_event(audit_id: str, kind: str):
    """kind = 'open' | 'click'"""
    with _events_lock:
        db = _load(EVENTS_DB)
        entry = db.setdefault(audit_id, {"opens": [], "clicks": []})
        entry[kind + "s"].append(datetime.datetime.utcnow().isoformat())
        _save(EVENTS_DB, db)

def get_events(audit_id: str) -> dict:
    return _load(EVENTS_DB).get(audit_id, {"opens": [], "clicks": []})


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/checkout/<audit_id>")
def checkout(audit_id):
    lead = get_lead(audit_id)
    if not lead:
        abort(404)
    isrc = lead.get("isrc", "")
    redacted = (isrc[:7] + "****") if len(isrc) >= 7 else "XXXXXXXXX"
    return render_template("checkout.html",
                           lead=lead,
                           redacted_isrc=redacted,
                           audit_id=audit_id)


@app.route("/pay/<audit_id>", methods=["POST"])
def pay(audit_id):
    lead = get_lead(audit_id)
    if not lead:
        abort(404)
    if not stripe.api_key:
        return "Stripe not configured — add STRIPE_SECRET_KEY to .env", 500

    cs = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": f"Forensic Audit: {lead['artist']} - {lead['track']}",
                    "description": (
                        "SoundExchange Black Box Recovery Report | "
                        "ISRC Registry Audit | Full PDF + Legal Attestation"
                    ),
                },
                "unit_amount": PRICE_CENTS,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=(
            url_for("payment_success", _external=True)
            + f"?session_id={{CHECKOUT_SESSION_ID}}&audit_id={audit_id}"
        ),
        cancel_url=url_for("lawyer_page", audit_id=audit_id, _external=True),
        metadata={"audit_id": audit_id},
    )
    return redirect(cs.url, code=303)


@app.route("/payment-success")
def payment_success():
    sid      = request.args.get("session_id", "")
    audit_id = request.args.get("audit_id", "")
    if not sid or not audit_id:
        abort(400)
    try:
        cs = stripe.checkout.Session.retrieve(sid)
        if cs.payment_status == "paid":
            mark_paid(audit_id, sid)
    except Exception:
        abort(400)
    # After payment, go back to lawyer page so they can download immediately
    return redirect(url_for("lawyer_page", audit_id=audit_id))


# ── Artist face scan (free, before payment) ───────────────────────────────────
@app.route("/preview/<audit_id>")
def preview(audit_id):
    lead = get_lead(audit_id)
    if not lead:
        abort(404)
    scan = get_scan_entry(audit_id)
    return render_template("preview.html",
                           lead=lead,
                           audit_id=audit_id,
                           already_scanned=scan is not None,
                           scan_sha=scan["sha256"] if scan else None)

@app.route("/preview/scan-complete/<audit_id>", methods=["POST"])
def preview_scan_complete(audit_id):
    if not get_lead(audit_id):
        return jsonify({"error": "not found"}), 404
    sha = mark_artist_scanned(audit_id)
    return jsonify({"ok": True, "sha256": sha})

@app.route("/api/scan-status/<audit_id>")
def scan_status(audit_id):
    scan = get_scan_entry(audit_id)
    paid = is_paid(audit_id)
    result = {"scanned": scan is not None, "paid": paid}
    if scan:
        result["sha256"] = scan["sha256"]
        result["scanned_at"] = scan["scanned_at"]
    if paid and scan:
        result["download_token"] = issue_download_token(audit_id)
    return jsonify(result)


# ── Lawyer landing page ───────────────────────────────────────────────────────
@app.route("/lawyer/<audit_id>")
def lawyer_page(audit_id):
    audit_id = audit_id.strip("-")
    lead = get_lead(audit_id)
    if not lead:
        abort(404)

    # Track email clicks — log when link from email is followed
    if request.args.get("src") == "email":
        threading.Thread(target=log_event, args=(audit_id, "click"), daemon=True).start()

    isrc = lead.get("isrc", "")
    redacted = (isrc[:7] + "****") if len(isrc) >= 7 else "XXXXXXXXX"
    scan = get_scan_entry(audit_id)
    paid = is_paid(audit_id)
    download_token = None
    if paid:
        download_token = issue_download_token(audit_id)
    return render_template("lawyer.html",
                           lead=lead,
                           audit_id=audit_id,
                           redacted_isrc=redacted,
                           scan=scan,
                           paid=paid,
                           download_token=download_token)


@app.route("/pixel/<audit_id>.gif")
def tracking_pixel(audit_id):
    """1×1 transparent GIF — embed in email HTML to track opens."""
    if get_lead(audit_id):
        threading.Thread(target=log_event, args=(audit_id, "open"), daemon=True).start()
    resp = app.response_class(
        response=io.BytesIO(_PIXEL_GIF).read(),
        status=200,
        mimetype="image/gif",
    )
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/api/email-events")
def email_events_api():
    """Return all email events — used by dashboard to show open/click status."""
    return jsonify(_load(EVENTS_DB))


@app.route("/biometric/<audit_id>")
def biometric_gate(audit_id):
    # Legacy route — redirect to new lawyer page
    return redirect(url_for("lawyer_page", audit_id=audit_id))


@app.route("/help")
def help_page():
    return render_template("help.html")


# ── WebAuthn endpoints ────────────────────────────────────────────────────────
@app.route("/webauthn/register-options", methods=["POST"])
def wa_register_options():
    if not _WA_LIB:
        return jsonify({"error": "webauthn library not installed"}), 500

    audit_id = (request.json or {}).get("audit_id", "")
    if not is_paid(audit_id):
        return jsonify({"error": "not paid"}), 403

    lead    = get_lead(audit_id)
    user_id = hashlib.sha256(audit_id.encode()).digest()[:16]

    opts = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=user_id,
        user_name=lead.get("artist", audit_id),
        user_display_name=f"{lead.get('artist')} Audit",
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            user_verification=UserVerificationRequirement.REQUIRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
        supported_pub_key_algs=[COSEAlgorithmIdentifier.ECDSA_SHA_256],
    )

    session["reg_challenge"] = opts.challenge.hex()
    session["reg_audit_id"]  = audit_id
    return jsonify(json.loads(options_to_json(opts)))


@app.route("/webauthn/register-verify", methods=["POST"])
def wa_register_verify():
    audit_id      = session.get("reg_audit_id")
    challenge_hex = session.get("reg_challenge")
    if not audit_id or not challenge_hex:
        return jsonify({"error": "no session"}), 400

    try:
        result = verify_registration_response(
            credential=request.json,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            expected_challenge=bytes.fromhex(challenge_hex),
        )
        store_credential(audit_id, {
            "id":         result.credential_id.hex(),
            "public_key": result.credential_public_key.hex(),
            "sign_count": result.sign_count,
        })
        token = issue_download_token(audit_id)
        return jsonify({"ok": True, "token": token, "audit_id": audit_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/webauthn/auth-options", methods=["POST"])
def wa_auth_options():
    if not _WA_LIB:
        return jsonify({"error": "webauthn library not installed"}), 500

    audit_id = (request.json or {}).get("audit_id", "")
    if not is_paid(audit_id):
        return jsonify({"error": "not paid"}), 403

    cred = get_credential(audit_id)
    if not cred:
        return jsonify({"error": "no credential registered"}), 400

    opts = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=bytes.fromhex(cred["id"]))
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    session["auth_challenge"] = opts.challenge.hex()
    session["auth_audit_id"]  = audit_id
    return jsonify(json.loads(options_to_json(opts)))


@app.route("/webauthn/auth-verify", methods=["POST"])
def wa_auth_verify():
    audit_id      = session.get("auth_audit_id")
    challenge_hex = session.get("auth_challenge")
    if not audit_id or not challenge_hex:
        return jsonify({"error": "no session"}), 400

    cred_stored = get_credential(audit_id)
    if not cred_stored:
        return jsonify({"error": "not registered"}), 400

    try:
        result = verify_authentication_response(
            credential=request.json,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            expected_challenge=bytes.fromhex(challenge_hex),
            credential_public_key=bytes.fromhex(cred_stored["public_key"]),
            credential_current_sign_count=cred_stored["sign_count"],
        )
        cred_stored["sign_count"] = result.new_sign_count
        store_credential(audit_id, cred_stored)
        token = issue_download_token(audit_id)
        return jsonify({"ok": True, "token": token, "audit_id": audit_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Download ──────────────────────────────────────────────────────────────────
@app.route("/download-redirect/<audit_id>")
def download_redirect(audit_id):
    if not is_paid(audit_id):
        abort(403)
    token = issue_download_token(audit_id)
    return redirect(url_for("download", audit_id=audit_id, token=token))


@app.route("/download/<audit_id>/<token>")
def download(audit_id, token):
    db    = _load(PAID_DB)
    entry = db.get(audit_id, {})
    if entry.get("download_token") != token:
        abort(403)

    lead = get_lead(audit_id)
    if not lead:
        abort(404)

    artist   = lead.get("artist", "").replace(" ", "_")
    track    = lead.get("track",  "")[:20].replace(" ", "_")
    pdf_name = f"{artist}_{track}_Audit.pdf"
    pdf_path = os.path.join(PDFS_DIR, pdf_name)

    if not os.path.exists(pdf_path):
        # PDF not yet generated — generate it on the fly
        from outreach.pdf_generator import generate_pdf
        pdf_path = generate_pdf(
            artist=lead.get("artist", ""),
            track=lead.get("track", ""),
            isrc=lead.get("isrc", ""),
            streams_input=lead.get("streams", 0),
        )

    # Anchor PDF hash on Monad in background
    def _anchor_pdf():
        try:
            with open(pdf_path, "rb") as f:
                pdf_sha = hashlib.sha256(f.read()).hexdigest()
            result = anchor_pdf(
                audit_id, lead.get("artist",""), lead.get("track",""),
                lead.get("isrc",""), pdf_sha
            )
            if "tx" in result:
                db2 = _load(PAID_DB)
                db2.setdefault(audit_id, {})["pdf_monad_tx"] = result["tx"]
                db2[audit_id]["pdf_monad_block"] = result["block"]
                _save(PAID_DB, db2)
        except Exception:
            pass
    threading.Thread(target=_anchor_pdf, daemon=True).start()

    # Invalidate token (one-time use)
    db[audit_id]["download_token"] = None
    _save(PAID_DB, db)

    return send_file(pdf_path, as_attachment=True, download_name=pdf_name)


if __name__ == "__main__":
    print(f"[WEB] WebAuthn lib: {_WA_LIB} | WA enabled: {WA_ENABLED}")
    print(f"[WEB] RP_ID: {RP_ID} | ORIGIN: {ORIGIN}")
    app.run(host="0.0.0.0", port=5001, debug=False)
