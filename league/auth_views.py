from django.contrib.auth.views import LoginView
from django.shortcuts import redirect


class FastlapLoginView(LoginView):
    template_name = "registration/login_v2.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("league:home")
        return super().dispatch(request, *args, **kwargs)
