from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class AdminRequiredMixin(LoginRequiredMixin):
    """Restricts a view to Admin-role members only (used for Modify/CRUD)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_admin_role:
            messages.error(request, "Only Admin users can modify stock records.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)
