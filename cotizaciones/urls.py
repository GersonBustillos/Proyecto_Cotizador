from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(
        template_name='cotizaciones/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    path('nueva/', views.nueva_cotizacion, name='nueva_cotizacion'),
    path('historial/', views.historial, name='historial'),
    path('<int:pk>/', views.detalle_cotizacion, name='detalle_cotizacion'),
    path('<int:pk>/editar/', views.nueva_cotizacion, name='editar_cotizacion'),
    path('<int:pk>/pdf/', views.generar_pdf, name='generar_pdf'),
    path('api/herramienta/<int:pk>/', views.api_herramienta, name='api_herramienta'),
    path('api/cliente/<int:pk>/', views.api_cliente, name='api_cliente'),
    path('<int:pk>/enviar/', views.enviar_cotizacion, name='enviar_cotizacion'),
    path('<int:pk>/aprobar/', views.aprobar_cotizacion, name='aprobar_cotizacion'),
    path('bandeja/', views.bandeja_aprobaciones, name='bandeja_aprobaciones'),
]