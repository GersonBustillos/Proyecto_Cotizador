from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Cotizacion, Herramienta, Cliente
from .forms import CotizacionForm, ItemCotizacionFormSet
from django.core.mail import EmailMessage
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
import json
from datetime import datetime
from django.db.models import Q
import csv
from django.http import HttpResponse
from django.core.cache import cache
import qrcode
from io import BytesIO
import base64
from django_otp.plugins.otp_totp.models import TOTPDevice
from django.contrib.auth import login
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken


def nueva_cotizacion(request, pk=None):
    if pk:
        cotizacion_existente = get_object_or_404(Cotizacion, pk=pk)
        
        # REGLA: Si la cotización ya tiene número (fue guardada) y no está rechazada, 
        # entra en bloqueo para el vendedor.
        es_gerencia = request.user.groups.filter(name='Gerencia General').exists() or request.user.is_superuser
        
        # Si ya fue guardada (tiene numero), no está rechazada y el vendedor intenta editarla:
        if cotizacion_existente.numero and cotizacion_existente.estado != 'rechazada' and not es_gerencia:
            messages.error(request, "La cotización ya fue guardada y enviada a revisión. Para modificarla, un aprobador debe rechazarla o aprobarla definitivamente.")
            return redirect('detalle_cotizacion', pk=pk)

    else:
        cotizacion_existente = None

    if request.method == 'POST':
        form = CotizacionForm(request.POST, instance=cotizacion_existente)
        if form.is_valid():
            cotizacion = form.save(commit=False)
            if not cotizacion.pk:
                cotizacion.creado_por = request.user
            else:
                # Si se está editando una cotización ya aprobada, se reinicia el flujo
                if cotizacion.nivel_aprobacion == 'nivel_3':
                    cotizacion.nivel_aprobacion = 'pendiente'
                    cotizacion.estado = 'borrador'
                    messages.warning(request, "La cotización fue modificada. Requiere una nueva aprobación.")
            cotizacion.save()
            form.save_m2m()
            formset = ItemCotizacionFormSet(request.POST, instance=cotizacion)
            
            if formset.is_valid():
                errores_precio = []
                items_guardados = 0
                
                for item_form in formset:
                    # 1. Ignorar si la fila está marcada para borrar
                    if item_form.cleaned_data.get('DELETE'):
                        continue
                        
                    herramienta = item_form.cleaned_data.get('herramienta')
                    cantidad = item_form.cleaned_data.get('cantidad')
                    precio_ingresado = item_form.cleaned_data.get('precio_unit_mensual')
                    
                    # 2. Si la fila está TOTALMENTE vacía, la ignoramos (es la fila extra)
                    if not herramienta and not cantidad and precio_ingresado is None:
                        continue
                        
                    # 3. SEGURIDAD: Si no está totalmente vacía, DEBE tener todos los datos
                    if not herramienta or not cantidad or precio_ingresado is None:
                        errores_precio.append("Hay una herramienta a la que le falta la cantidad o el precio mensual.")
                        continue
                        
                    items_guardados += 1
                    
                    # 4. Validar precios contra la lista (tu lógica original)
                    rango = herramienta.rango_para_cantidad(cantidad, cotizacion.contrato_minimo_meses)
                    if not rango:
                        continue

                    if cotizacion.tipo == 'partner':
                        precio_lista = rango.precio_partner
                    elif cotizacion.tipo == 'telco':
                        precio_lista = rango.precio_telco
                    else:
                        precio_lista = rango.precio_regular

                    if precio_lista is not None and precio_ingresado < precio_lista:
                        errores_precio.append(
                            f"{herramienta.nombre}: precio {precio_ingresado} es menor al precio de lista {precio_lista} para este rango."
                        )

                    if cotizacion.tipo == 'cliente_final':
                        precio_especial_ingresado = item_form.cleaned_data.get('precio_unit_especial')
                        precio_lista_especial = rango.precio_especial
                        if (precio_especial_ingresado is not None
                                and precio_lista_especial is not None
                                and precio_especial_ingresado < precio_lista_especial):
                            errores_precio.append(
                                f"{herramienta.nombre}: precio especial {precio_especial_ingresado} es menor al precio de lista {precio_lista_especial} para este rango."
                            )

                # 5. Verificamos que no haya errores y que al menos haya una herramienta
                if not errores_precio and items_guardados == 0:
                    errores_precio.append("Debes agregar al menos una herramienta válida a la cotización.")

                if errores_precio:
                    form.add_error(None, "No se puede guardar: " + " | ".join(errores_precio))
                else:
                    formset.save()
                    if not cotizacion.numero:
                        cotizacion.numero = cotizacion.generar_numero()
                        cotizacion.save(update_fields=['numero'])
                    return redirect('detalle_cotizacion', pk=cotizacion.pk)
            elif not cotizacion_existente:
                cotizacion.delete()
        else:
            formset = ItemCotizacionFormSet(request.POST, instance=cotizacion_existente)

    else:
        form = CotizacionForm(instance=cotizacion_existente)
        formset = ItemCotizacionFormSet(instance=cotizacion_existente)

    # NUEVO: Forzar que los campos de la fila extra vacía no sean obligatorios en el HTML
    if formset:
        for item_form in formset:
            for field in item_form.fields.values():
                field.required = False

    return render(request, 'cotizaciones/nueva_cotizacion.html', {
        'form': form,
        'formset': formset,
        'editando': cotizacion_existente is not None,
    })

def historial(request):
    # 1. Traemos todas las cotizaciones inicialmente
    cotizaciones = Cotizacion.objects.select_related('cliente', 'creado_por').order_by('-fecha')
    
    # 2. REGLA DE PRIVACIDAD: Si no es aprobador ni superusuario, solo ve las suyas
    grupos_aprobadores = ['Jefe Comercial', 'Jefe Cotizaciones', 'Gerencia General']
    es_aprobador = request.user.groups.filter(name__in=grupos_aprobadores).exists()
    
    if not es_aprobador and not request.user.is_superuser:
        cotizaciones = cotizaciones.filter(creado_por=request.user)

    # 3. Aplicar filtros de búsqueda
    tipo = request.GET.get('tipo')
    cliente_q = request.GET.get('cliente')
    numero_q = request.GET.get('numero')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if tipo:
        cotizaciones = cotizaciones.filter(tipo=tipo)
    if cliente_q:
        cotizaciones = cotizaciones.filter(cliente__nombre_empresa__icontains=cliente_q)
    if numero_q:
        cotizaciones = cotizaciones.filter(numero__icontains=numero_q)
    
    # Filtro por fechas
    if fecha_inicio:
        cotizaciones = cotizaciones.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        cotizaciones = cotizaciones.filter(fecha__date__lte=fecha_fin)

    total_resultados = cotizaciones.count()

    return render(request, 'cotizaciones/historial.html', {
        'cotizaciones': cotizaciones,
        'total_resultados': total_resultados
    })

@login_required
def detalle_cotizacion(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    
    # 🛡️ BARRERA DE SEGURIDAD
    grupos_aprobadores = ['Jefe Comercial', 'Jefe Cotizaciones', 'Gerencia General']
    es_aprobador = request.user.groups.filter(name__in=grupos_aprobadores).exists()
    es_creador = cotizacion.creado_por == request.user
    
    # Si no es jefe, ni creador, ni superusuario -> Bloqueado
    if not (es_aprobador or es_creador or request.user.is_superuser):
        messages.error(request, "No tienes permiso para ver esta cotización.")
        return redirect('historial')

    return render(request, 'cotizaciones/detalle_cotizacion.html', {'cotizacion': cotizacion})

def api_herramienta(request, pk):
    h = get_object_or_404(Herramienta, pk=pk)

    cantidad = request.GET.get('cantidad')
    meses_contrato = request.GET.get('meses_contrato')

    rango = None
    if cantidad:
        try:
            cantidad = int(cantidad)
            meses_contrato = int(meses_contrato) if meses_contrato else 12
            rango = h.rango_para_cantidad(cantidad, meses_contrato)
        except (ValueError, TypeError):
            rango = None

    if rango:
        data = {
            'precio_partner': str(rango.precio_partner) if rango.precio_partner is not None else '',
            'precio_regular': str(rango.precio_regular) if rango.precio_regular is not None else '',
            'precio_especial': str(rango.precio_especial) if rango.precio_especial is not None else '',
            'precio_telco': str(rango.precio_telco) if rango.precio_telco is not None else '',
            'rango_usado': True,
            'meses_contrato_usado': rango.meses_contrato,
        }
    else:
        data = {
            'precio_partner': str(h.precio_partner) if h.precio_partner is not None else '',
            'precio_regular': str(h.precio_regular) if h.precio_regular is not None else '',
            'precio_especial': str(h.precio_especial) if h.precio_especial is not None else '',
            'precio_telco': str(h.precio_telco) if h.precio_telco is not None else '',
            'rango_usado': False,
            'meses_contrato_usado': None,
        }

    data['caracteristicas'] = h.caracteristicas
    return JsonResponse(data)


def api_cliente(request, pk):
    c = get_object_or_404(Cliente, pk=pk)
    data = {'tipo_cliente': c.tipo_cliente}
    if c.pais:
        data['moneda_default'] = c.pais.moneda_default
        data['terminos_default'] = c.pais.terminos_default
    else:
        data['moneda_default'] = ''
        data['terminos_default'] = ''
    return JsonResponse(data)

from django.http import HttpResponse
from weasyprint import HTML
import os
from pathlib import Path
from django.conf import settings

@login_required
def generar_pdf(request, pk):
    import re
    import unicodedata

    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    # NUEVO: Bloqueo de seguridad
    # Si no está aprobado, solo puede verlo si está en los grupos de aprobación o si es el creador
    grupos_aprobadores = ['Jefe Comercial', 'Jefe Cotizaciones', 'Gerencia General']
    es_aprobador = request.user.groups.filter(name__in=grupos_aprobadores).exists()
    es_creador = cotizacion.creado_por == request.user
    
    if cotizacion.nivel_aprobacion != 'nivel_3' and not (es_aprobador or es_creador or request.user.is_superuser):
        messages.error(request, "No tienes permiso para ver esta cotización.")
        return redirect('historial')


    caracteristicas_lista = [linea.strip() for linea in cotizacion.caracteristicas.split('\n') if linea.strip()]

    logo_path = Path(settings.BASE_DIR, 'cotizaciones', 'static', 'cotizaciones', 'img', 'logo.png').as_uri()

    html_string = render(request, 'cotizaciones/pdf_cotizacion.html', {
        'cotizacion': cotizacion,
        'caracteristicas_lista': caracteristicas_lista,
        'logo_path': logo_path,
    }).content.decode('utf-8')

    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    def limpiar(texto):
        texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
        return re.sub(r'[^A-Za-z0-9]', '', texto)

    cliente_limpio = limpiar(cotizacion.cliente.nombre_empresa)
    nombre_archivo = f"Cotizacion-{cotizacion.pk:04d}-{cliente_limpio}-{cotizacion.numero}.pdf"

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    return response
# Create your views here.

@login_required
def enviar_cotizacion(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
        # NUEVO: BLOQUEO DE SEGURIDAD
    # Si la cotización no está aprobada (nivel 3), no se puede enviar.
    # (A menos que seas el superusuario o de Gerencia, si quieres dar esa excepción).
    if cotizacion.nivel_aprobacion != 'nivel_3' and not request.user.is_superuser:
        messages.error(request, "No puedes enviar esta cotización porque aún no ha sido aprobada por Gerencia General.")
        return redirect('detalle_cotizacion', pk=cotizacion.pk)
    # 1. Recolectar destinatarios
    destinatarios = [v.email for v in cotizacion.vendedores.all() if v.email]
    
    if cotizacion.correos_adicionales:
        extras = [c.strip() for c in cotizacion.correos_adicionales.split(',') if c.strip()]
        destinatarios.extend(extras)
        
    if not destinatarios:
        messages.error(request, "No hay correos configurados para enviar esta cotización.")
        return redirect('detalle_cotizacion', pk=cotizacion.pk)

    # 2. Generar el PDF (reutilizamos la lógica de tu vista generar_pdf)
    # Para no duplicar código, extraemos el PDF de la vista original
    import re
    import unicodedata
    from weasyprint import HTML
    from pathlib import Path
    
    caracteristicas_lista = [linea.strip() for linea in cotizacion.caracteristicas.split('\n') if linea.strip()]
    logo_path = Path(settings.BASE_DIR, 'cotizaciones', 'static', 'cotizaciones', 'img', 'logo.png').as_uri()

    html_string = render(request, 'cotizaciones/pdf_cotizacion.html', {
        'cotizacion': cotizacion,
        'caracteristicas_lista': caracteristicas_lista,
        'logo_path': logo_path,
    }).content.decode('utf-8')

    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    # 3. Armar y enviar el correo
    asunto = f"Cotización {cotizacion.numero} - {cotizacion.cliente.nombre_empresa}"
    cuerpo = f"Estimados,\n\nAdjunto encontrarán la cotización {cotizacion.numero} correspondiente al plan: {cotizacion.plan_nombre}.\n\nQuedamos atentos a sus comentarios.\n\nSaludos cordiales,\nEquipo NUVO"
    
    email = EmailMessage(
        asunto,
        cuerpo,
        settings.DEFAULT_FROM_EMAIL,
        destinatarios,
    )
    
    # Nombre del archivo
    def limpiar(texto):
        texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
        return re.sub(r'[^A-Za-z0-9]', '', texto)
    
    cliente_limpio = limpiar(cotizacion.cliente.nombre_empresa)
    nombre_archivo = f"Cotizacion-{cotizacion.pk:04d}-{cliente_limpio}-{cotizacion.numero}.pdf"
    
    email.attach(nombre_archivo, pdf_file, 'application/pdf')
    email.send()

    # 4. Actualizar estado en la base de datos
    cotizacion.estado = 'enviada'
    cotizacion.correo_enviado = True
    cotizacion.save(update_fields=['estado', 'correo_enviado'])

    messages.success(request, f"La cotización fue enviada exitosamente a: {', '.join(destinatarios)}")
    return redirect('detalle_cotizacion', pk=cotizacion.pk)

@login_required
def aprobar_cotizacion(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)

    if request.user.groups.filter(name='Jefe Comercial').exists():
        nivel_actual = 'nivel_1'
    elif request.user.groups.filter(name='Jefe Cotizaciones').exists():
        nivel_actual = 'nivel_2'
    elif request.user.groups.filter(name='Gerencia General').exists():
        nivel_actual = 'nivel_3'
    else:
        messages.error(request, "No tienes permisos para aprobar cotizaciones.")
        return redirect('historial')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        comentario = request.POST.get('comentario', '')
        
        # Validar que el nivel que intenta aprobar sea el correcto
        if cotizacion.nivel_aprobacion != 'pendiente' and nivel_actual == 'nivel_1':
             messages.error(request, "Esta cotización ya pasó el Nivel 1.")
             return redirect('detalle_cotizacion', pk=pk)
             
        if accion == 'aprobar':
            # REGLA: Si el Jefe de Cotizaciones (nivel 2) aprueba, se convierte en APROBADA FINAL.
            if nivel_actual == 'nivel_2':
                cotizacion.nivel_aprobacion = 'nivel_3'
                cotizacion.estado = 'aprobada'
                messages.success(request, "¡Cotización aprobada definitivamente por el Jefe de Cotizaciones!")
            else:
                cotizacion.nivel_aprobacion = nivel_actual
                if nivel_actual == 'nivel_3':
                    cotizacion.estado = 'aprobada'
                messages.success(request, f"¡Aprobación registrada en el {nivel_actual.replace('_', ' ').title()}!")
            
        elif accion == 'escalar':
            if nivel_actual == 'nivel_2':
                cotizacion.nivel_aprobacion = 'nivel_2' # Se queda en nivel 2 pero listo para nivel 3
                messages.info(request, "Cotización escalada a Gerencia General para revisión excepcional.")
            else:
                messages.warning(request, "Solo el Jefe de Cotizaciones puede escalar a Gerencia.")
                return redirect('detalle_cotizacion', pk=pk)
                
        elif accion == 'rechazar':
            cotizacion.nivel_aprobacion = 'rechazado'
            cotizacion.estado = 'rechazada'
            messages.error(request, "Cotización rechazada.")
            
        cotizacion.comentarios_aprobacion = comentario
        cotizacion.save()
        return redirect('detalle_cotizacion', pk=pk)

    return render(request, 'cotizaciones/aprobar_cotizacion.html', {
        'cotizacion': cotizacion,
        'nivel_actual': nivel_actual
    })


@login_required
def bandeja_aprobaciones(request):
    # 1. Determinar el rol del usuario y los estados que le corresponden
    if request.user.groups.filter(name='Jefe Comercial').exists():
        estados_pendientes = ['pendiente']
        estados_historial = ['nivel_1', 'nivel_2', 'nivel_3', 'rechazado']
        titulo = 'Jefe Comercial (Nivel 1)'
    elif request.user.groups.filter(name='Jefe Cotizaciones').exists():
        estados_pendientes = ['nivel_1']
        estados_historial = ['nivel_2', 'nivel_3', 'rechazado']
        titulo = 'Jefe de Cotizaciones (Nivel 2)'
    elif request.user.groups.filter(name='Gerencia General').exists():
        estados_pendientes = ['nivel_2']
        estados_historial = ['nivel_3', 'rechazado']
        titulo = 'Gerencia General (Nivel 3)'
    else:
        messages.error(request, "No tienes permisos para acceder a la bandeja de aprobaciones.")
        return redirect('historial')

    # 2. Ver qué pestaña quiere ver el usuario (pendientes por defecto)
    vista = request.GET.get('vista', 'pendientes')
    
    if vista == 'historial':
        cotizaciones = Cotizacion.objects.filter(nivel_aprobacion__in=estados_historial).order_by('-fecha')
        es_historial = True
    else:
        cotizaciones = Cotizacion.objects.filter(nivel_aprobacion__in=estados_pendientes).order_by('-fecha')
        es_historial = False

    return render(request, 'cotizaciones/bandeja_aprobaciones.html', {
        'cotizaciones': cotizaciones,
        'titulo_bandeja': titulo,
        'es_historial': es_historial,
        'vista_actual': vista
    })

@login_required
def dashboard(request):
    # 1. Obtener fechas del formulario
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin')

    hoy = timezone.now().date()
    
    # Por defecto, si no hay filtros, mostramos el mes actual
    if not fecha_inicio_str:
        fecha_inicio_str = hoy.replace(day=1).strftime('%Y-%m-%d')
    if not fecha_fin_str:
        fecha_fin_str = hoy.strftime('%Y-%m-%d')

    # Convertir strings a fechas reales para la consulta
    fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
    fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

    # --- NUEVO PASO 3: REGLA DE PRIVACIDAD ---
    # 2. Base de datos inicial
    cotizaciones_base = Cotizacion.objects.all()
    
    # Verificamos si el usuario es aprobador
    grupos_aprobadores = ['Jefe Comercial', 'Jefe Cotizaciones', 'Gerencia General']
    es_aprobador = request.user.groups.filter(name__in=grupos_aprobadores).exists()
    
    # Si NO es aprobador y NO es superusuario, solo ve sus propias cotizaciones
    if not es_aprobador and not request.user.is_superuser:
        cotizaciones_base = cotizaciones_base.filter(creado_por=request.user)
    # -----------------------------------------

    # 3. Filtrar cotizaciones por el rango de fechas (sobre la base ya filtrada)
    cotizaciones_filtradas = cotizaciones_base.filter(
        fecha__date__gte=fecha_inicio,
        fecha__date__lte=fecha_fin
    )

    # 4. Estadísticas
    total_cotizaciones = cotizaciones_filtradas.count()
    aprobadas = cotizaciones_filtradas.filter(estado='aprobada').count()
    pendientes = cotizaciones_filtradas.exclude(estado__in=['aprobada', 'rechazada']).count()

    # 5. Datos para Gráficos
    estados_data = [
        cotizaciones_filtradas.filter(estado='borrador').count(),
        cotizaciones_filtradas.filter(estado='enviada').count(),
        cotizaciones_filtradas.filter(estado='aprobada').count(),
        cotizaciones_filtradas.filter(estado='rechazada').count(),
    ]

    top_clientes = cotizaciones_filtradas.values('cliente__nombre_empresa').annotate(
        total=Count('id')
    ).order_by('-total')[:5]

    ultimas_cotizaciones = cotizaciones_filtradas.select_related('cliente').order_by('-fecha')[:5]

    context = {
        'total_cotizaciones': total_cotizaciones,
        'aprobadas': aprobadas,
        'pendientes': pendientes,
        'estados_data': json.dumps(estados_data),
        'top_clientes_labels': json.dumps([c['cliente__nombre_empresa'] for c in top_clientes]),
        'top_clientes_data': json.dumps([c['total'] for c in top_clientes]),
        'ultimas_cotizaciones': ultimas_cotizaciones,
        # Pasamos las fechas al HTML para que se queden seleccionadas en los inputs
        'fecha_inicio': fecha_inicio_str,
        'fecha_fin': fecha_fin_str,
    }
    return render(request, 'cotizaciones/dashboard.html', context)

@login_required
def duplicar_cotizacion(request, pk):
    original = get_object_or_404(Cotizacion, pk=pk)
    
    # 1. Copiamos el objeto principal (ponemos pk=None para que se cree uno nuevo)
    nueva = Cotizacion.objects.get(pk=original.pk)
    nueva.pk = None 
    nueva.numero = '' # Se generará uno nuevo automáticamente
    nueva.estado = 'borrador'
    nueva.nivel_aprobacion = 'pendiente'
    nueva.correo_enviado = False
    nueva.creado_por = request.user
    nueva.fecha = timezone.now()
    nueva.save()
    
    # 2. Copiamos los vendedores asignados (ManyToMany)
    nueva.vendedores.set(original.vendedores.all())
    
    # 3. Copiamos las herramientas (los ítems)
    for item in original.items.all():
        item.pk = None
        item.cotizacion = nueva
        item.save()
        
    # 4. Generamos el nuevo número y guardamos
    nueva.numero = nueva.generar_numero()
    nueva.save(update_fields=['numero'])
    
    messages.success(request, f"Se ha creado una copia de la cotización {original.numero}.")
    
    # Redirigimos directo a editar la nueva cotización
    return redirect('editar_cotizacion', pk=nueva.pk)

@login_required
def exportar_excel(request):
    # 🛡️ BARRERA ANTI-SATURACIÓN
    # Creamos una llave única por usuario (ej: "limite_export_5")
    cache_key = f"limite_export_{request.user.id}"
    
    # Si la llave existe, significa que exportó hace menos de 10 segundos
    if cache.get(cache_key):
        messages.warning(request, "Por favor, espera unos segundos antes de volver a exportar el Excel.")
        return redirect('historial')
        
    # Guardamos en caché por 10 segundos
    cache.set(cache_key, True, timeout=10)

    # --- A partir de aquí sigue tu código normal ---
    
    # 1. REGLA DE PRIVACIDAD
    cotizaciones = Cotizacion.objects.select_related('cliente', 'creado_por').order_by('-fecha')
    
    grupos_aprobadores = ['Jefe Comercial', 'Jefe Cotizaciones', 'Gerencia General']
    es_aprobador = request.user.groups.filter(name__in=grupos_aprobadores).exists()
    
    if not es_aprobador and not request.user.is_superuser:
        cotizaciones = cotizaciones.filter(creado_por=request.user)

    # 2. Aplicar los mismos filtros de búsqueda del historial
    tipo = request.GET.get('tipo')
    cliente_q = request.GET.get('cliente')
    numero_q = request.GET.get('numero')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if tipo: cotizaciones = cotizaciones.filter(tipo=tipo)
    if cliente_q: cotizaciones = cotizaciones.filter(cliente__nombre_empresa__icontains=cliente_q)
    if numero_q: cotizaciones = cotizaciones.filter(numero__icontains=numero_q)
    if fecha_inicio: cotizaciones = cotizaciones.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin: cotizaciones = cotizaciones.filter(fecha__date__lte=fecha_fin)

    # 3. Crear el archivo CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="Reporte_Cotizaciones.csv"'
    response.write('\ufeff'.encode('utf8')) # Para que Excel reconozca las tildes y eñes

    writer = csv.writer(response)
    # Cabeceras del Excel
    writer.writerow(['Número', 'Creado por', 'Cliente', 'País', 'Tipo', 'Fecha', 'Estado', 'Aprobación', 'Total Mensual (Ref)', 'Moneda'])

    # 4. Recorrer las cotizaciones y escribir las filas
    for c in cotizaciones:
        writer.writerow([
            c.numero,
            c.creado_por.username if c.creado_por else "N/A",
            c.cliente.nombre_empresa,
            c.cliente.pais.pais if c.cliente.pais else "-",
            c.get_tipo_display(),
            c.fecha.strftime("%d/%m/%Y %H:%M"),
            c.get_estado_display(),
            c.get_nivel_aprobacion_display(),
            # Sumamos los totales mensuales (si es que tiene items)
            sum([item.total_mensual for item in c.items.all()]),
            c.moneda
        ])

    return response

@login_required
def configurar_mfa(request):
    # Si el usuario ya tiene un dispositivo confirmado, lo mandamos al dashboard
    if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
        return redirect('dashboard')

    # Buscamos o creamos un dispositivo no confirmado
    device, created = TOTPDevice.objects.get_or_create(user=request.user, confirmed=False)
    
    if request.method == 'POST':
        token = request.POST.get('token')
        if device.verify_token(token):
            device.confirmed = True
            device.save()
            messages.success(request, "¡MFA configurado correctamente!")
            return redirect('dashboard')
        else:
            messages.error(request, "Código incorrecto. Inténtalo de nuevo.")

    # Generamos el código QR
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(device.config_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    qr_image = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'cotizaciones/mfa_setup.html', {
        'qr_image': qr_image,
        'secret_key': device.key,
        'device_id': device.id,
    })

@login_required
def verificar_mfa(request):
    # Si ya está verificado, lo pasamos al dashboard
    if request.user.is_verified():
        return redirect('dashboard')
        
    if request.method == 'POST':
        token = request.POST.get('token')
        # Buscamos los dispositivos confirmados del usuario
        devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
        
        for device in devices:
            if device.verify_token(token):
                # ¡ESTA ES LA LÍNEA MÁGICA QUE FALTABA!
                # Registra el dispositivo como verificado en la sesión
                otp_login(request, device) 
                return redirect('dashboard')
                
        messages.error(request, "Código incorrecto o expirado. Inténtalo de nuevo.")
        
    return render(request, 'cotizaciones/mfa_verify.html')
from django_otp.plugins.otp_static.models import StaticDevice

@login_required
def codigos_respaldo(request):
    # Buscamos o creamos el dispositivo de códigos estáticos para el usuario
    device, created = StaticDevice.objects.get_or_create(user=request.user, name='backup')
    
    if request.method == 'POST':
        # Borramos los códigos anteriores
        device.token_set.all().delete()
        
        # Generamos 10 nuevos códigos
        codigos = []
        for _ in range(10):
            # Usamos StaticToken.random_token() en lugar de device.token_generator()
            token = StaticToken.random_token()
            device.token_set.create(token=token)
            codigos.append(token)
        
        messages.success(request, "Se han generado 10 nuevos códigos de respaldo.")
        return render(request, 'cotizaciones/codigos_respaldo.html', {
            'codigos': codigos, 
            'generados': True
        })
        
    # Si es una petición GET, mostramos la pantalla con el botón para generar
    return render(request, 'cotizaciones/codigos_respaldo.html', {
        'generados': False
    })