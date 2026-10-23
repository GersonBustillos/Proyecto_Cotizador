from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView, LogoutView
from cotizaciones import views
from cotizaciones.forms import SimpleOTPAuthenticationForm

urlpatterns = [
    # 1. El panel de administración tiene su propio login nativo
    path('admin/', admin.site.urls),
    
    # 2. El login del sistema (MFA) va en la raíz
    path('login/', LoginView.as_view(
        template_name='cotizaciones/login.html',
        authentication_form=SimpleOTPAuthenticationForm
    ), name='login'),
    
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('setup/', views.configurar_mfa, name='otp_setup'),
    path('verify/', views.verificar_mfa, name='otp_verify'),
    path('respaldo/', views.codigos_respaldo, name='codigos_respaldo'),
    
    # 3. Las rutas de la app
    path('cotizaciones/', include('cotizaciones.urls')),
]