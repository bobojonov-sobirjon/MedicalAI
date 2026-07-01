"""Create fixed demo account for App Store / Google Play review."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.demo import demo_credentials_public, demo_account_enabled, ensure_demo_account


class Command(BaseCommand):
    help = "Create or update the fixed demo account (login/password/OTP never change)."

    def handle(self, *args, **options):
        if not demo_account_enabled():
            self.stdout.write(
                self.style.WARNING(
                    "DEMO_ACCOUNT_ENABLED=false — set DEMO_ACCOUNT_ENABLED=true in .env and run again."
                )
            )
            return

        user = ensure_demo_account()
        creds = demo_credentials_public()
        self.stdout.write(self.style.SUCCESS(f"Demo account ready (id={user.pk})"))
        self.stdout.write(f"  identifier: {creds['email']}  (or username: {creds['username']})")
        self.stdout.write(f"  password:   {creds['password']}")
        self.stdout.write(f"  OTP code:   {creds['otp_code']}")
