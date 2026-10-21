from django.contrib import admin
from .models import Cliente, Herramienta, Cotizacion, ItemCotizacion

from .models import Cliente, Herramienta, Cotizacion, ItemCotizacion, Pais, RangoPrecio, Vendedor


@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ('pais', 'nombre', 'telefono', 'email', 'sitio_web', 'nombre_impuesto', 'moneda_default')

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre_empresa', 'tipo_cliente', 'pais', 'contacto', 'email', 'telefono')
    list_filter = ('tipo_cliente', 'pais')
    search_fields = ('nombre_empresa',)
    
@admin.register(Vendedor)
class VendedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'email', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'email')

class RangoPrecioInline(admin.TabularInline):
    model = RangoPrecio
    extra = 1
    fields = ('meses_contrato', 'cantidad_min', 'cantidad_max', 'precio_telco', 'precio_partner', 'precio_especial', 'precio_regular')
    ordering = ('meses_contrato', 'cantidad_min')


@admin.register(Herramienta)
class HerramientaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio_telco', 'precio_partner', 'precio_regular', 'precio_especial')
    search_fields = ('nombre',)
    inlines = [RangoPrecioInline]



class ItemCotizacionInline(admin.TabularInline):
    model = ItemCotizacion
    extra = 1


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ('numero', 'cliente', 'tipo', 'fecha', 'estado')
    list_filter = ('tipo', 'estado')
    search_fields = ('numero', 'cliente__nombre_empresa')
    inlines = [ItemCotizacionInline]
