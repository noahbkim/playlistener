from django.core.management.base import BaseCommand
from core.models import Invitation, User


class Command(BaseCommand):
    """Invite a user to setup integrations."""

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--admin", action="store_true", default=False)
        parser.add_argument("--delete", action="store_true", default=False)

    def handle(self, username, *args, **options):
        """Allow invitations to be overwritten with permissions."""

        if options["delete"]:
            User.objects.filter(username=username).delete()
            return

        invitation, created = Invitation.objects.get_or_create(username=username)
        invitation.administrator = options["admin"]
        invitation.save()
