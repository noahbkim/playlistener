from django.core.management.base import BaseCommand, CommandError
from core.models import Invitation


class Command(BaseCommand):
    """Invite a user to setup integrations."""

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--admin", action="store_true", default=False)

    def handle(self, username, *args, **options):
        Invitation.objects.create(username=username, administrator=options["admin"])
