from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Cotizacion, Herramienta, Cliente
from .forms import CotizacionForm, ItemCotizacionFormSet


def nueva_cotizacion(request, pk=None):
    if pk:
        cotizacion_existente = get_object_or_404(Cotizacion, pk=pk)
    else:
        cotizacion_existente = None

    if request.method == 'POST':
        form = CotizacionForm(request.POST, instance=cotizacion_existente)
        if form.is_valid():
            cotizacion = form.save(commit=False)
            if not cotizacion.pk:
                cotizacion.creado_por = request.user
            cotizacion.save()
            form.save_m2m()
            formset = ItemCotizacionFormSet(request.POST, instance=cotizacion)
            if formset.is_valid():
                errores_precio = []
                for item_form in formset:
                    if not item_form.cleaned_data or item_form.cleaned_data.get('DELETE'):
                        continue
                    herramienta = item_form.cleaned_data.get('herramienta')
                    cantidad = item_form.cleaned_data.get('cantidad')
                    precio_ingresado = item_form.cleaned_data.get('precio_unit_mensual')
                    if not herramienta or not cantidad or precio_ingresado is None:
                        continue

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

                if errores_precio:
                    for error in errores_precio:
                        formset.errors  # fuerza evaluación de errors ya generado
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
