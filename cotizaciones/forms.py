from django import forms
from django.forms import inlineformset_factory
from .models import Cotizacion, ItemCotizacion
from django_otp.forms import OTPAuthenticationForm


class CotizacionForm(forms.ModelForm):
    class Meta:
        model = Cotizacion
        fields = ['cliente', 'tipo', 'plan_nombre', 'caracteristicas',
                  'contrato_minimo_meses', 'duracion_oferta_dias', 'moneda',
                  'terminos_condiciones', 'color_primario',
                  'vendedores', 'correos_adicionales']
        widgets = {
            'vendedores': forms.SelectMultiple(attrs={'class': 'form-select', 'id': 'id_vendedores'}),
            'correos_adicionales': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'correo1@ejemplo.com, correo2@ejemplo.com'}),
            'cliente': forms.Select(attrs={'class': 'form-select', 'id': 'id_cliente'}),
            'tipo': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo'}),
            'plan_nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'caracteristicas': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'contrato_minimo_meses': forms.NumberInput(attrs={'class': 'form-control'}),
            'duracion_oferta_dias': forms.NumberInput(attrs={'class': 'form-control'}),
            'moneda': forms.Select(attrs={'class': 'form-select', 'id': 'id_moneda'}),
            'terminos_condiciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'id': 'id_terminos_condiciones'}),
            'color_primario': forms.TextInput(attrs={'class': 'form-control', 'type': 'color', 'style': 'height: 42px;'}),
        }

class ItemCotizacionForm(forms.ModelForm):
    class Meta:
        model = ItemCotizacion
        fields = ['herramienta', 'cantidad', 'precio_unit_mensual', 'precio_unit_especial']
        widgets = {
            # Aquí están los 'required': False que te mencioné para evitar el error de la fila vacía
            'herramienta': forms.Select(attrs={'class': 'form-select herramienta-select', 'required': False}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control cantidad-input', 'required': False}),
            'precio_unit_mensual': forms.NumberInput(attrs={'class': 'form-control precio-mensual-input', 'step': '0.01', 'required': False}),
            'precio_unit_especial': forms.NumberInput(attrs={'class': 'form-control precio-especial-input', 'step': '0.01', 'required': False}),
        }


ItemCotizacionFormSet = inlineformset_factory(
    Cotizacion, ItemCotizacion,
    form=ItemCotizacionForm,
    extra=1, 
    can_delete=True,
    validate_min=False,
    min_num=0
)

from django.contrib.auth.forms import AuthenticationForm
from django import forms

class SimpleOTPAuthenticationForm(AuthenticationForm):
    # Este campo es opcional y lo usaremos después para el paso 2
    otp_token = forms.CharField(required=False, widget=forms.HiddenInput)
    
    # Forzamos a que el formulario no exija el token OTP
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        if 'otp_token' in self.fields:
            self.fields['otp_token'].required = False