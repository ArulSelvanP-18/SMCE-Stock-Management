from django.core.management.base import BaseCommand
from django.db import transaction

from stock.catalog import seed_catalog
from stock.models import Member


class Command(BaseCommand):
    help = "Initializes SMCE Stock Management: seeds the block/department catalog and optionally creates an Admin user."

    def add_arguments(self, parser):
        parser.add_argument("--admin-username", type=str, default=None)
        parser.add_argument("--admin-password", type=str, default=None)
        parser.add_argument("--admin-fullname", type=str, default="System Administrator")

    @transaction.atomic
    def handle(self, *args, **options):
        seed_catalog()
        self.stdout.write(self.style.SUCCESS("Block/department catalog seeded successfully."))

        username = options.get("admin_username")
        password = options.get("admin_password")
        if username and password:
            if Member.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(f"User '{username}' already exists — skipping."))
            else:
                Member.objects.create_superuser(
                    username=username,
                    password=password,
                    full_name=options.get("admin_fullname"),
                    role=Member.ROLE_ADMIN,
                )
                self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' created."))
