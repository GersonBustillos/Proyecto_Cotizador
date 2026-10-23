from django.shortcuts import redirect
from django_otp import user_has_device

class ForceMFAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Si el usuario es superusuario y está en el admin, lo dejamos pasar sin MFA
        if request.user.is_authenticated and request.user.is_superuser and request.path.startswith('/admin/'):
            return self.get_response(request)

        if request.user.is_authenticated:
            # Rutas que SIEMPRE deben estar permitidas (para no crear bucles)
            # Incluimos login, logout, setup, verify y static
            allowed_paths = ['/login/', '/logout/', '/setup/', '/verify/', '/respaldo/']
            
            # 1. Si NO tiene dispositivo MFA configurado, lo mandamos a configurarlo
            if not user_has_device(request.user) and not any(request.path.startswith(p) for p in allowed_paths):
                return redirect('otp_setup')
            
            # 2. Si YA tiene MFA configurado pero no está verificado en esta sesión, lo mandamos a verificar
            if user_has_device(request.user) and not request.user.is_verified():
                # Verificamos que no esté ya en la página de verificación o configuración para evitar el bucle
                if not request.path.startswith('/verify/') and not request.path.startswith('/setup/'):
                    return redirect('otp_verify')

        response = self.get_response(request)
        return response