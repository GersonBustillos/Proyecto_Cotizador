from django.db import models
from decimal import Decimal

MONEDA_CHOICES = [
    ('USD', 'USD - Dólar estadounidense'),
    ('EUR', 'EUR - Euro'),
    ('PEN', 'PEN - Sol peruano'),
    ('CLP', 'CLP - Peso chileno'),
    ('COP', 'COP - Peso colombiano'),
    ('MXN', 'MXN - Peso mexicano'),
    ('ARS', 'ARS - Peso argentino'),
    ('BRL', 'BRL - Real brasileño'),
    ('BOB', 'BOB - Boliviano'),
    ('UYU', 'UYU - Peso uruguayo'),
    ('PYG', 'PYG - Guaraní paraguayo'),
    ('VES', 'VES - Bolívar venezolano'),
    ('GTQ', 'GTQ - Quetzal guatemalteco'),
    ('CRC', 'CRC - Colón costarricense'),
    ('PAB', 'PAB - Balboa panameño'),
    ('DOP', 'DOP - Peso dominicano'),
    ('HNL', 'HNL - Lempira hondureño'),
    ('NIO', 'NIO - Córdoba nicaragüense'),
    ('CAD', 'CAD - Dólar canadiense'),
    ('GBP', 'GBP - Libra esterlina'),
    ('CHF', 'CHF - Franco suizo'),
    ('JPY', 'JPY - Yen japonés'),
    ('CNY', 'CNY - Yuan chino'),
    ('AUD', 'AUD - Dólar australiano'),
    ('NZD', 'NZD - Dólar neozelandés'),
    ('INR', 'INR - Rupia india'),
    ('KRW', 'KRW - Won surcoreano'),
    ('SGD', 'SGD - Dólar de Singapur'),
    ('HKD', 'HKD - Dólar de Hong Kong'),
    ('SEK', 'SEK - Corona sueca'),
    ('NOK', 'NOK - Corona noruega'),
    ('DKK', 'DKK - Corona danesa'),
    ('PLN', 'PLN - Zloty polaco'),
    ('RUB', 'RUB - Rublo ruso'),
    ('TRY', 'TRY - Lira turca'),
    ('ZAR', 'ZAR - Rand sudafricano'),
    ('AED', 'AED - Dirham de EAU'),
    ('SAR', 'SAR - Riyal saudí'),
    ('ILS', 'ILS - Shekel israelí'),
    ('THB', 'THB - Baht tailandés'),
    ('IDR', 'IDR - Rupia indonesia'),
    ('MYR', 'MYR - Ringgit malayo'),
    ('PHP', 'PHP - Peso filipino'),
    ('VND', 'VND - Dong vietnamita'),
]


class Pais(models.Model):
    """Catálogo de países/sedes, con sus datos de contacto e impuesto."""
    pais = models.CharField(max_length=100, help_text="Ej: Perú, Chile, Colombia, España, Miami")
    nombre = models.CharField(max_length=100, unique=True, help_text="Razón social de la sede, ej: NUVO SAC")
    telefono = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    sitio_web = models.CharField(max_length=200, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    nombre_impuesto = models.CharField(
        max_length=20, default='IGV',
        help_text="Ej: IGV (Perú), IVA (Chile, Colombia, España)"
    )
    moneda_default = models.CharField(
        max_length=10, default='USD', choices=MONEDA_CHOICES,
        help_text="Moneda que se sugiere por defecto para este país"
    )
    terminos_default = models.TextField(
        blank=True,
        help_text="Una condición por línea. Se auto-completará en la cotización al elegir un cliente de este país."
    )

    class Meta:
        verbose_name = "País"
        verbose_name_plural = "Países"

    def __str__(self):
        return f"{self.pais} — {self.nombre}"

class Vendedor(models.Model):
    """Catálogo de vendedores a quienes se les envían las cotizaciones aprobadas."""
    nombre = models.CharField(max_length=150)
    email = models.EmailField()
    activo = models.BooleanField(default=True, help_text="Desmarcar para ocultarlo de la lista sin borrarlo")

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.email})"

class Cliente(models.Model):
    TIPO_CLIENTE_CHOICES = [
        ('partner', 'Partner'),
        ('cliente_final', 'Cliente Final'),
        ('telco', 'Telco'),
    ]

    nombre_empresa = models.CharField(max_length=200)
    tipo_cliente = models.CharField(max_length=20, choices=TIPO_CLIENTE_CHOICES, default='cliente_final')
    pais = models.ForeignKey(Pais, on_delete=models.PROTECT, null=True, blank=True)
    contacto = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.nombre_empresa

class Herramienta(models.Model):
    """Catálogo de las 30 herramientas. Se carga una sola vez."""
    nombre = models.CharField(max_length=150, unique=True)
    codigo = models.CharField(
        max_length=10, blank=True,
        help_text="Código corto para el número de cotización, ej: SAP para Saas Protection"
    )
    caracteristicas = models.TextField(
        blank=True,
        help_text="Una característica por línea. Se auto-completará en la cotización al elegir esta herramienta."
    )
    precio_partner = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_regular = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_especial = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_telco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.nombre
    
    def rango_para_cantidad(self, cantidad, meses_contrato=12):
        from django.db.models import Q

        meses_disponibles = list(
            self.rangos_precio.order_by().values_list('meses_contrato', flat=True).distinct()
        )
        if not meses_disponibles:
            return None

        meses_mas_cercano = min(meses_disponibles, key=lambda m: abs(m - meses_contrato))

        return self.rangos_precio.filter(
            meses_contrato=meses_mas_cercano,
            cantidad_min__lte=cantidad
        ).filter(
            Q(cantidad_max__gte=cantidad) | Q(cantidad_max__isnull=True)
        ).order_by('cantidad_min').first()

class RangoPrecio(models.Model):
    """Precio escalonado por rango de cantidad y plazo de contrato, para una herramienta."""
    herramienta = models.ForeignKey(Herramienta, related_name='rangos_precio', on_delete=models.CASCADE)
    meses_contrato = models.PositiveIntegerField(
        default=12,
        help_text="Plazo de contrato al que aplica esta tabla de precios (ej: 12, 24, 36)"
    )
    cantidad_min = models.PositiveIntegerField()
    cantidad_max = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Dejar vacío para 'X a más' (sin límite superior)"
    )
    precio_telco = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_partner = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_especial = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_regular = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['meses_contrato', 'cantidad_min']
        verbose_name = "Rango de Precio"
        verbose_name_plural = "Rangos de Precio"

    def __str__(self):
        rango = f"{self.cantidad_min} a {self.cantidad_max}" if self.cantidad_max else f"{self.cantidad_min} a más"
        return f"{self.herramienta.nombre} — {self.meses_contrato} meses ({rango})"

class Cotizacion(models.Model):
    TIPO_CHOICES = [
        ('partner', 'Partner'),
        ('cliente_final', 'Cliente Final'),
        ('telco', 'Telco'),
    ]
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('enviada', 'Enviada'),
        ('aprobada', 'Aprobada'),
        ('rechazada', 'Rechazada'),
    ]

    numero = models.CharField(max_length=80, unique=True, blank=True, editable=False)
    fecha = models.DateTimeField(auto_now_add=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    plan_nombre = models.CharField(max_length=200, help_text="Ej: Retención de Backup Ilimitada")
    caracteristicas = models.TextField(help_text="Una característica por línea")
    contrato_minimo_meses = models.PositiveIntegerField(default=12)
    duracion_oferta_dias = models.PositiveIntegerField(default=30)
    moneda = models.CharField(max_length=10, default='USD', choices=MONEDA_CHOICES)
    terminos_condiciones = models.TextField(
        blank=True,
        help_text="Una condición por línea"
    )
    color_primario = models.CharField(
        max_length=7, default='#1a73c1',
        help_text="Color principal del PDF en formato hexadecimal, ej: #1a73c1"
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    vendedores = models.ManyToManyField(
        Vendedor, blank=True, related_name='cotizaciones',
        help_text="Vendedores del catálogo a quienes se les enviará esta cotización"
    )
    correos_adicionales = models.TextField(
        blank=True,
        help_text="Correos extra no registrados en el catálogo, separados por coma"
    )
    correo_enviado = models.BooleanField(default=False, editable=False)
    creado_por = models.ForeignKey(
        'auth.User', on_delete=models.PROTECT, null=True, blank=True,
        related_name='cotizaciones_creadas'
    )
    # --- NUEVOS CAMPOS PARA EL FLUJO DE APROBACIÓN ---
    NIVEL_APROBACION_CHOICES = [
        ('pendiente', 'Pendiente de Aprobación (Nivel 1)'),
        ('nivel_1', 'Aprobado por Jefe Comercial (Pasa a Nivel 2)'),
        ('nivel_2', 'Aprobado por Jefe de Cotizaciones (Pasa a Nivel 3)'),
        ('nivel_3', 'Aprobado por Gerencia General (Final)'),
        ('rechazado', 'Rechazado'),
    ]
    nivel_aprobacion = models.CharField(
        max_length=20, 
        choices=NIVEL_APROBACION_CHOICES, 
        default='pendiente',
        help_text="Indica en qué nivel del flujo de aprobación se encuentra"
    )
    comentarios_aprobacion = models.TextField(
        blank=True, 
        help_text="Observaciones o motivos de rechazo del aprobador"
    )

    def generar_numero(self):
        import re
        import unicodedata

        def limpiar(texto):
            texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
            return re.sub(r'[^A-Za-z0-9]', '', texto)

        from django.utils import timezone
        fecha_local = timezone.localtime(self.fecha)
        fecha_str = fecha_local.strftime('%d%m%Y%H%M')

        codigos = [c for c in self.items.values_list('herramienta__codigo', flat=True) if c]
        if not codigos:
            codigo_final = 'GEN'
        elif len(codigos) == 1:
            codigo_final = codigos[0]
        elif len(codigos) == 2:
            codigo_final = f"{codigos[0]}-{codigos[1]}"
        else:
            codigo_final = f"{codigos[0]}-MULTI"

        return f"{codigo_final}{fecha_str}"

    @property
    def nombre_herramientas(self):
        nombres = list(self.items.values_list('herramienta__nombre', flat=True))
        if not nombres:
            return self.plan_nombre
        return ' + '.join(nombres)


class ItemCotizacion(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, related_name='items', on_delete=models.CASCADE)
    herramienta = models.ForeignKey(Herramienta, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unit_mensual = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unit_especial = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    @property
    def total_mensual(self):
        return self.cantidad * self.precio_unit_mensual

    @property
    def total_anual(self):
        return self.total_mensual * 12

    @property
    def total_mensual_especial(self):
        if self.precio_unit_especial:
            return self.cantidad * self.precio_unit_especial
        return None

    @property
    def total_anual_especial(self):
        if self.total_mensual_especial:
            return self.total_mensual_especial * 12
        return None

    def __str__(self):
        return f"{self.herramienta} x{self.cantidad}"

# Create your models here.
