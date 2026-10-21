from django import template

register = template.Library()


@register.filter
def moneda_pe(valor):
    """Formatea un número como 1,234.56 (coma miles, punto decimales)."""
    if valor is None or valor == '':
        return '-'
    try:
        numero = float(valor)
    except (ValueError, TypeError):
        return valor
    return f"{numero:,.2f}"