from django.urls import path
from . import views

urlpatterns = [
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
    path('dashboard/', views.dashboard, name='dashboard'),
    path('<int:pk>/duplicar/', views.duplicar_cotizacion, name='duplicar_cotizacion'),
    path('exportar/', views.exportar_excel, name='exportar_excel'),
]