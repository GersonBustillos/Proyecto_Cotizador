from .models import Cotizacion

def notificaciones_aprobacion(request):
    if not request.user.is_authenticated:
        return {}
        
    count = 0
    if request.user.groups.filter(name='Jefe Comercial').exists():
        count = Cotizacion.objects.filter(nivel_aprobacion='pendiente').count()
    elif request.user.groups.filter(name='Jefe Cotizaciones').exists():
        count = Cotizacion.objects.filter(nivel_aprobacion='nivel_1').count()
    elif request.user.groups.filter(name='Gerencia General').exists():
        count = Cotizacion.objects.filter(nivel_aprobacion='nivel_2').count()

    return {'notificaciones_count': count}