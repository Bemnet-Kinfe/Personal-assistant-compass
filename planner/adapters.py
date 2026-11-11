"""Who may create an account.

Compass is a personal app: sign-up is closed unless SIGNUP_OPEN is on, and when
ALLOWED_EMAILS is set only those addresses may join (by password or Google).
Existing accounts, such as the seeded demo account, can always sign in.
"""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


def email_allowed(email):
    if not settings.ALLOWED_EMAILS:
        return True
    return bool(email) and email.strip().lower() in settings.ALLOWED_EMAILS


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return settings.SIGNUP_OPEN

    def clean_email(self, email):
        email = super().clean_email(email)
        if not email_allowed(email):
            from django import forms

            raise forms.ValidationError("This Compass only accepts invited email addresses.")
        return email


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        email = next((e.email for e in sociallogin.email_addresses if e.email), sociallogin.user.email)
        return bool(settings.ALLOWED_EMAILS) and email_allowed(email) or (settings.SIGNUP_OPEN and email_allowed(email))
