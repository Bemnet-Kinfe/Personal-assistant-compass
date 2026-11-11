from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Area


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def give_new_users_default_areas(sender, instance, created, **kwargs):
    if created:
        Area.create_defaults(instance)
