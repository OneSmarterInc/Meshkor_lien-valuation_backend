r"""Create or update a portal user.

  python backend\manage.py create_portal_user --email jane@firm.com --password ... --role firm --firm "Smith & Lee LLP"
  python backend\manage.py create_portal_user --email me@meshkor.com --password ... --role admin
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Firm, Profile


class Command(BaseCommand):
    help = "Create or update a portal user (firm / reviewer / admin)."

    def add_arguments(self, p):
        p.add_argument("--email", required=True)
        p.add_argument("--password", required=True)
        p.add_argument("--role", choices=[r.value for r in Profile.Role], default="firm")
        p.add_argument("--firm", help="Firm name (required for role firm; created if missing)")
        p.add_argument("--name", default="", help="Full name shown in the portal")

    def handle(self, *a, **o):
        User = get_user_model()
        firm = None
        if o["role"] == "firm":
            if not o["firm"]:
                raise CommandError("--firm is required for role firm")
            firm, _ = Firm.objects.get_or_create(name=o["firm"].strip())
        user, created = User.objects.get_or_create(email__iexact=o["email"], defaults={"username": o["email"], "email": o["email"]})
        user.set_password(o["password"])
        if o["name"]:
            parts = o["name"].split(" ", 1)
            user.first_name, user.last_name = parts[0], (parts[1] if len(parts) > 1 else "")
        user.is_active = True
        user.save()
        Profile.objects.update_or_create(user=user, defaults={"role": o["role"], "firm": firm})
        self.stdout.write(f"{'created' if created else 'updated'} {user.email} role={o['role']} firm={firm or '-'}")
