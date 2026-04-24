from __future__ import annotations

import json
import os
from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials as firebase_credentials
import jwt
import requests
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests


@dataclass(frozen=True)
class SocialProfile:
    provider: str
    provider_user_id: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class FirebaseAuthService:
    @staticmethod
    def _service_account_from_env() -> dict | None:
        """
        Build a Firebase service account dict from env vars.

        Expected env keys (matching Google service account JSON):
        - FIREBASE_TYPE
        - FIREBASE_PROJECT_ID
        - FIREBASE_PRIVATE_KEY_ID
        - FIREBASE_PRIVATE_KEY (may contain literal '\\n')
        - FIREBASE_CLIENT_EMAIL
        - FIREBASE_CLIENT_ID
        - FIREBASE_AUTH_URI
        - FIREBASE_TOKEN_URI
        - FIREBASE_AUTH_PROVIDER_CERT_URL
        - FIREBASE_CLIENT_CERT_URL
        """

        def _get(name: str) -> str:
            return (os.getenv(name) or "").strip()

        private_key = _get("FIREBASE_PRIVATE_KEY")
        # dotenv often stores multiline keys with literal "\n"
        if private_key:
            if (private_key.startswith('"') and private_key.endswith('"')) or (
                private_key.startswith("'") and private_key.endswith("'")
            ):
                private_key = private_key[1:-1]
            private_key = private_key.replace("\\n", "\n")

        service_account = {
            "type": _get("FIREBASE_TYPE"),
            "project_id": _get("FIREBASE_PROJECT_ID"),
            "private_key_id": _get("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": private_key,
            "client_email": _get("FIREBASE_CLIENT_EMAIL"),
            "client_id": _get("FIREBASE_CLIENT_ID"),
            "auth_uri": _get("FIREBASE_AUTH_URI"),
            "token_uri": _get("FIREBASE_TOKEN_URI"),
            "auth_provider_x509_cert_url": _get("FIREBASE_AUTH_PROVIDER_CERT_URL"),
            "client_x509_cert_url": _get("FIREBASE_CLIENT_CERT_URL"),
        }

        # Require a minimal set; otherwise treat as not configured.
        required = ("type", "project_id", "private_key", "client_email")
        if any(not (service_account.get(k) or "").strip() for k in required):
            return None
        return service_account

    @staticmethod
    def _get_app() -> firebase_admin.App:
        """
        Initialize Firebase Admin SDK once.

        Env options:
        - FIREBASE_SERVICE_ACCOUNT_FILE: path to serviceAccountKey.json
        - FIREBASE_SERVICE_ACCOUNT_JSON: raw JSON content (string)
        - FIREBASE_* keys: individual fields (type, project_id, private_key, etc.)
        """
        if firebase_admin._apps:
            return firebase_admin.get_app()

        sa_path = (os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE") or "").strip()
        sa_json = (os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or "").strip()

        if sa_path:
            cred = firebase_credentials.Certificate(sa_path)
        elif sa_json:
            cred = firebase_credentials.Certificate(json.loads(sa_json))
        else:
            sa_env = FirebaseAuthService._service_account_from_env()
            if sa_env:
                cred = firebase_credentials.Certificate(sa_env)
            else:
                raise ValueError(
                    "Firebase is not configured. Set FIREBASE_SERVICE_ACCOUNT_FILE, "
                    "FIREBASE_SERVICE_ACCOUNT_JSON, or FIREBASE_* service account env vars"
                )

        return firebase_admin.initialize_app(cred)

    @staticmethod
    def verify_id_token(id_token: str) -> SocialProfile:
        """
        Verifies Firebase ID token produced by Firebase Auth (Google/Apple/etc).
        Returns a normalized profile.
        """
        if not id_token:
            raise ValueError("id_token is required")
        FirebaseAuthService._get_app()
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=False)

        uid = decoded.get("uid") or decoded.get("sub")
        if not uid:
            raise ValueError("Invalid Firebase token (uid missing)")

        email = decoded.get("email")
        name = decoded.get("name") or ""
        first_name = decoded.get("given_name") or (name.split(" ")[0] if name else None)
        last_name = decoded.get("family_name") or (" ".join(name.split(" ")[1:]) if " " in name else None)

        # Best-effort provider detection
        provider = "firebase"
        firebase_info = decoded.get("firebase") or {}
        sign_in_provider = firebase_info.get("sign_in_provider") or ""
        if "google" in sign_in_provider:
            provider = "google"
        elif "apple" in sign_in_provider:
            provider = "apple"

        return SocialProfile(
            provider=provider,
            provider_user_id=str(uid),
            email=email,
            first_name=first_name,
            last_name=last_name,
        )


class SocialAuthService:
    @staticmethod
    def verify_google_id_token(token: str) -> SocialProfile:
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        if not client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured")
        payload = google_id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
        sub = payload.get("sub")
        if not sub:
            raise ValueError("Google token is missing sub")
        return SocialProfile(
            provider="google",
            provider_user_id=sub,
            email=payload.get("email"),
            first_name=payload.get("given_name"),
            last_name=payload.get("family_name"),
        )

    @staticmethod
    def verify_apple_identity_token(token: str) -> SocialProfile:
        """
        Apple Sign-In identityToken verification using Apple's JWKS.
        Required env: APPLE_CLIENT_ID (a.k.a. Services ID / Bundle ID).
        """
        client_id = os.getenv("APPLE_CLIENT_ID", "").strip()
        if not client_id:
            raise ValueError("APPLE_CLIENT_ID is not configured")

        jwks = requests.get("https://appleid.apple.com/auth/keys", timeout=10).json()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k))
                break
        if key is None:
            raise ValueError("Apple public key not found for kid")

        payload = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=client_id,
            issuer="https://appleid.apple.com",
            options={"verify_exp": True},
        )
        sub = payload.get("sub")
        if not sub:
            raise ValueError("Apple token is missing sub")
        return SocialProfile(provider="apple", provider_user_id=sub, email=payload.get("email"))

    @staticmethod
    def verify_vk(code_or_access_token: str, is_code: bool, platform: str | None = None) -> SocialProfile:
        """
        VK OAuth verification.
        - If is_code=True, exchanges code to access_token via oauth.vk.com
        - Then fetches user info via users.get
        Required env (choose one of):
          - VK_CLIENT_ID, VK_CLIENT_SECRET (single app for all)
          - VK_ANDROID_CLIENT_ID, VK_ANDROID_CLIENT_SECRET (Android)
          - VK_IOS_CLIENT_ID, VK_IOS_CLIENT_SECRET (iOS)
        Also required:
          VK_REDIRECT_URI
        """
        platform_norm = (platform or "").strip().lower()
        if platform_norm not in ("", "android", "ios"):
            raise ValueError("platform must be 'android' or 'ios' (optional)")

        # Prefer platform-specific credentials if provided.
        if platform_norm == "android":
            client_id = (os.getenv("VK_ANDROID_CLIENT_ID") or os.getenv("VK_CLIENT_ID") or "").strip()
            client_secret = (os.getenv("VK_ANDROID_CLIENT_SECRET") or os.getenv("VK_CLIENT_SECRET") or "").strip()
        elif platform_norm == "ios":
            client_id = (os.getenv("VK_IOS_CLIENT_ID") or os.getenv("VK_CLIENT_ID") or "").strip()
            client_secret = (os.getenv("VK_IOS_CLIENT_SECRET") or os.getenv("VK_CLIENT_SECRET") or "").strip()
        else:
            client_id = (os.getenv("VK_CLIENT_ID") or "").strip()
            client_secret = (os.getenv("VK_CLIENT_SECRET") or "").strip()
            # If generic not set, but platform-specific exist, pick any (android preferred).
            if not client_id:
                client_id = (os.getenv("VK_ANDROID_CLIENT_ID") or os.getenv("VK_IOS_CLIENT_ID") or "").strip()
            if not client_secret:
                client_secret = (os.getenv("VK_ANDROID_CLIENT_SECRET") or os.getenv("VK_IOS_CLIENT_SECRET") or "").strip()

        redirect_uri = os.getenv("VK_REDIRECT_URI", "").strip()
        api_version = os.getenv("VK_API_VERSION", "5.199").strip()

        if not client_id or not client_secret or not redirect_uri:
            raise ValueError(
                "VK is not configured. Set VK_REDIRECT_URI and client credentials "
                "(VK_CLIENT_ID/VK_CLIENT_SECRET or VK_ANDROID_* / VK_IOS_*)"
            )

        access_token = code_or_access_token
        user_id = None
        email = None

        if is_code:
            resp = requests.get(
                "https://oauth.vk.com/access_token",
                params={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code_or_access_token,
                },
                timeout=10,
            ).json()
            if "error" in resp:
                raise ValueError(resp.get("error_description") or resp.get("error") or "VK code exchange failed")
            access_token = resp.get("access_token")
            user_id = resp.get("user_id")
            email = resp.get("email")

        if not access_token:
            raise ValueError("VK access_token is missing")

        # If user_id not provided, resolve via users.get (requires user_id? we can call with v + access_token only)
        user_resp = requests.get(
            "https://api.vk.com/method/users.get",
            params={
                "access_token": access_token,
                "v": api_version,
                "fields": "first_name,last_name",
            },
            timeout=10,
        ).json()
        if "error" in user_resp:
            raise ValueError(user_resp["error"].get("error_msg") or "VK users.get failed")
        user = (user_resp.get("response") or [{}])[0]
        user_id = user_id or user.get("id")
        if not user_id:
            raise ValueError("VK user id not resolved")

        return SocialProfile(
            provider="vk",
            provider_user_id=str(user_id),
            email=email,
            first_name=user.get("first_name"),
            last_name=user.get("last_name"),
        )


# Backward compatible stub (referenced by config/swagger_auth.py).
class SMSService:  # pragma: no cover
    pass

