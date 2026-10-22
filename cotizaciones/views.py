from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Cotizacion, Herramienta, Cliente
from .forms import CotizacionForm, ItemCotizacionFormSet
from django.core.mail import EmailMessage
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def nueva_cotizacion(request, pk=None):
    if pk:
        cotizacion_existente = get_object_or_404(Cotizacion, pk=pk)
        # NUEVO: Permitir editar si está pendiente/rechazada, O si eres el creador, O si eres Gerencia/Superusuario
        es_gerencia = request.user.groups.filter(name='Gerencia General').exists() or request.user.is_superuser
        es_creador = cotizacion_existente.creado_por == request.user
        
        if cotizacion_existente.nivel_aprobacion not in ['pendiente', 'rechazado'] and not es_gerencia and not es_creador:
            messages.error(request, "Esta cotización está en proceso de aprobación y no puede ser editada.")
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
    cotizaciones = Cotizacion.objects.select_related('cliente').order_by('-fecha')
    tipo = request.GET.get('tipo')
    cliente_q = request.GET.get('cliente')
    if tipo:
        cotizaciones = cotizaciones.filter(tipo=tipo)
    if cliente_q:
        cotizaciones = cotizaciones.filter(cliente__nombre_empresa__icontains=cliente_q)
    return render(request, 'cotizaciones/historial.html', {'cotizaciones': cotizaciones})


def detalle_cotizacion(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
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