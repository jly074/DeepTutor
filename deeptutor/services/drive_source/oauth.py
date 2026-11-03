"""Explicit, online-only Google OAuth; encrypted owner/workspace-bound local state.

No credentials are provisioned here. Only approved server environment configuration
can enable this adapter. No refresh token or background work is requested/stored.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlsplit

import httpx

from deeptutor.services.config import protected_settings

from .client import ID_PATTERN, DriveFailure

SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
CALLBACK = "/drive-oauth-callback"


class OAuthConfig:
    def __init__(self, client_id="", client_secret="", redirect_uri=""):
        self.client_id, self.client_secret, self.redirect_uri = (
            client_id,
            client_secret,
            redirect_uri,
        )

    @property
    def valid(self):
        try:
            p = urlsplit(self.redirect_uri)
            _ = p.port
        except ValueError:
            return False
        return bool(
            re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", self.client_id)
            and self.client_secret
            and len(self.client_secret) <= 4096
            and p.hostname
            and not p.username
            and not p.password
            and not p.query
            and not p.fragment
            and p.path == CALLBACK
            and (
                p.scheme == "https"
                or (p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost", "::1"))
            )
        )

    @property
    def origin(self):
        p = urlsplit(self.redirect_uri)
        return f"{p.scheme}://{p.netloc}"


def config():
    return OAuthConfig(
        *(
            os.environ.get(key, "")
            for key in (
                "DEEPTUTOR_GOOGLE_CLIENT_ID",
                "DEEPTUTOR_GOOGLE_CLIENT_SECRET",
                "DEEPTUTOR_GOOGLE_REDIRECT_URI",
            )
        )
    )


class OAuthStore:
    def __init__(self, path: Path, owner: str, workspace: str):
        self.path, self.owner, self.workspace = path, owner, workspace

    @contextmanager
    def connect(self):
        c = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(self.path, timeout=5)
            c.execute(
                "CREATE TABLE IF NOT EXISTS drive_oauth (owner TEXT, workspace TEXT, payload TEXT NOT NULL, PRIMARY KEY(owner,workspace))"
            )
            with c:
                yield c
        except (OSError, sqlite3.Error, protected_settings.ProtectionError):
            raise DriveFailure("storage_unavailable", 409) from None
        finally:
            if c is not None:
                c.close()

    def read(self):
        if not self.path.exists():
            return {}
        with self.connect() as c:
            row = c.execute(
                "SELECT payload FROM drive_oauth WHERE owner=? AND workspace=?",
                (self.owner, self.workspace),
            ).fetchone()
        if not row:
            return {}
        try:
            raw = json.loads(row[0])
            if (
                not isinstance(raw, dict)
                or raw.get("protected_format") != protected_settings.FORMAT
            ):
                raise ValueError()
            value = protected_settings.decode(raw)
            if (
                value.pop("_owner", None) != self.owner
                or value.pop("_workspace", None) != self.workspace
            ):
                raise ValueError()
            return value
        except (ValueError, OSError, protected_settings.ProtectionError):
            raise DriveFailure("storage_unavailable", 409) from None

    def write(self, value):
        try:
            envelope = protected_settings.encode(
                {**value, "_owner": self.owner, "_workspace": self.workspace}, self.path, force=True
            )
        except (OSError, protected_settings.ProtectionError):
            raise DriveFailure("storage_unavailable", 409) from None
        with self.connect() as c:
            c.execute(
                "INSERT INTO drive_oauth VALUES(?,?,?) ON CONFLICT(owner,workspace) DO UPDATE SET payload=excluded.payload",
                (self.owner, self.workspace, json.dumps(envelope)),
            )

    def consume(self, expected):
        # Atomic compare-and-swap: two callbacks cannot both redeem the same state.
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT payload FROM drive_oauth WHERE owner=? AND workspace=?",
                (self.owner, self.workspace),
            ).fetchone()
            if not row:
                raise DriveFailure("invalid_callback", 400)
            try:
                value = protected_settings.decode(json.loads(row[0]))
            except (ValueError, OSError, protected_settings.ProtectionError):
                raise DriveFailure("storage_unavailable", 409) from None
            if value.get("pending", {}).get("state_hash") != expected:
                raise DriveFailure("invalid_callback", 400)
            # Pending grant owns this row. Consume before contacting Google, even on failure.
            claim = secrets.token_urlsafe(32)
            envelope = protected_settings.encode(
                {"_owner": self.owner, "_workspace": self.workspace, "claim": claim},
                self.path,
                force=True,
            )
            c.execute(
                "UPDATE drive_oauth SET payload=? WHERE owner=? AND workspace=?",
                (json.dumps(envelope), self.owner, self.workspace),
            )

        return claim

    def finish(self, claim, value):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT payload FROM drive_oauth WHERE owner=? AND workspace=?",
                (self.owner, self.workspace),
            ).fetchone()
            current = protected_settings.decode(json.loads(row[0])) if row else {}
            if current.get("claim") != claim:
                raise DriveFailure("superseded_authorization", 409)
            envelope = protected_settings.encode(
                {**value, "_owner": self.owner, "_workspace": self.workspace}, self.path, force=True
            )
            c.execute(
                "UPDATE drive_oauth SET payload=? WHERE owner=? AND workspace=?",
                (json.dumps(envelope), self.owner, self.workspace),
            )

    def invalidate(self, connection_id):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT payload FROM drive_oauth WHERE owner=? AND workspace=?",
                (self.owner, self.workspace),
            ).fetchone()
            value = protected_settings.decode(json.loads(row[0])) if row else {}
            if value.get("connection_id") != connection_id:
                return
            envelope = protected_settings.encode(
                {"_owner": self.owner, "_workspace": self.workspace}, self.path, force=True
            )
            c.execute(
                "UPDATE drive_oauth SET payload=? WHERE owner=? AND workspace=?",
                (json.dumps(envelope), self.owner, self.workspace),
            )


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class DriveOAuth:
    def __init__(self, store: OAuthStore, settings: OAuthConfig, transport=None, clock=time.time):
        self.store, self.settings, self.transport, self.clock = store, settings, transport, clock
        # Anonymous local mode collapses all callers into a shared identity.
        self.authenticated = store.owner != "local-admin"

    def status(self):
        if not self.settings.valid:
            return {"state": "not_configured", "scope": SCOPE}
        if not self.authenticated:
            return {"state": "authentication_required", "scope": SCOPE}
        if not protected_settings.available():
            return {"state": "storage_unavailable", "scope": SCOPE}
        data = self.store.read()
        if data.get("access_token") and data.get("expires_at", 0) > self.clock() + 30:
            return {"state": "connected", "scope": SCOPE, "expires_at": data["expires_at"]}
        return {"state": "needs_authorization", "scope": SCOPE}

    def start(self, folder, browser_nonce, origin):
        current_state = self.status()["state"]
        if current_state in (
            "not_configured",
            "storage_unavailable",
            "authentication_required",
        ):
            raise DriveFailure(
                current_state, 401 if current_state == "authentication_required" else 409
            )
        if origin != self.settings.origin:
            raise DriveFailure("access_denied", 403)
        if not re.fullmatch(ID_PATTERN, folder) or not re.fullmatch(
            r"[A-Za-z0-9_-]{32,200}", browser_nonce
        ):
            raise DriveFailure("invalid_request", 422)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        self.store.write(
            {
                "pending": {
                    "state_hash": digest(state),
                    "nonce_hash": digest(browser_nonce),
                    "verifier": verifier,
                    "folder": folder,
                    "expires_at": self.clock() + 600,
                    "client_id": self.settings.client_id,
                    "redirect_uri": self.settings.redirect_uri,
                }
            }
        )
        return {
            "state": state,
            "authorization_url": AUTHORIZE
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.client_id,
                    "redirect_uri": self.settings.redirect_uri,
                    "response_type": "code",
                    "scope": SCOPE,
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "access_type": "online",
                    "include_granted_scopes": "false",
                    "prompt": "consent select_account",
                }
            ),
        }

    async def complete(self, state, nonce, code, error, origin):
        if not self.authenticated or not self.settings.valid or origin != self.settings.origin:
            raise DriveFailure("access_denied", 403)
        pending = self.store.read().get("pending", {})
        if (
            not state
            or not nonce
            or not secrets.compare_digest(pending.get("state_hash", ""), digest(state))
            or not secrets.compare_digest(pending.get("nonce_hash", ""), digest(nonce))
            or pending.get("expires_at", 0) <= self.clock()
            or pending.get("client_id") != self.settings.client_id
            or pending.get("redirect_uri") != self.settings.redirect_uri
        ):
            raise DriveFailure("invalid_callback", 400)
        claim = self.store.consume(digest(state))
        if error or not code:
            raise DriveFailure("consent_denied", 400)
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=15, follow_redirects=False
            ) as client:
                r = await client.post(
                    TOKEN,
                    data={
                        "client_id": self.settings.client_id,
                        "client_secret": self.settings.client_secret,
                        "redirect_uri": self.settings.redirect_uri,
                        "code": code,
                        "code_verifier": pending["verifier"],
                        "grant_type": "authorization_code",
                    },
                )
            if r.status_code != 200:
                raise DriveFailure("exchange_failed", 409)
            if len(r.content) > 65536:
                raise DriveFailure("invalid_response", 502)
            data = r.json()
            if (
                data.get("scope", "").split() != [SCOPE]
                or data.get("token_type", "").lower() != "bearer"
                or not isinstance(data.get("access_token"), str)
                or not 1 <= len(data["access_token"]) <= 8192
                or isinstance(data.get("expires_in"), bool)
                or not 30 <= int(data.get("expires_in", 0)) <= 3600
            ):
                raise DriveFailure("invalid_response", 502)
            self.store.finish(
                claim,
                {
                    "access_token": data["access_token"],
                    "expires_at": self.clock() + int(data["expires_in"]),
                    "folder": pending["folder"],
                    "connection_id": "google-" + secrets.token_hex(16),
                },
            )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, OverflowError):
            raise DriveFailure("exchange_failed", 409) from None
        return self.status()

    def disconnect(self, origin):
        if not self.authenticated or not self.settings.valid or origin != self.settings.origin:
            raise DriveFailure("access_denied", 403)
        self.store.write({})
        return {"state": "needs_authorization", "scope": SCOPE}

    def token(self):
        if not self.authenticated:
            raise DriveFailure("authentication_required", 401)
        data = self.store.read()
        return data.get("access_token") if data.get("expires_at", 0) > self.clock() + 30 else None


def get_drive_oauth():
    from deeptutor.multi_user.context import get_current_user
    from deeptutor.multi_user.paths import get_account_path_service
    from deeptutor.services.workspace.context import current_workspace_id

    user = get_current_user()
    from deeptutor.core.identities import is_partner_user_id

    if is_partner_user_id(user.id):
        raise DriveFailure("access_denied", 403)
    store = OAuthStore(
        get_account_path_service().get_settings_file("drive_oauth").with_suffix(".sqlite3"),
        user.scope.user_id,
        current_workspace_id(),
    )
    return DriveOAuth(store, config())
