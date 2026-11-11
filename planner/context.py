from django.conf import settings


def site(request):
    return {
        "APP_NAME": settings.APP_NAME,
        "ENVIRONMENT": settings.ENVIRONMENT,
        "GOOGLE_ENABLED": settings.GOOGLE_ENABLED,
        "SIGNUP_OPEN": settings.SIGNUP_OPEN,
    }
