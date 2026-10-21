from django.core.management.base import BaseCommand
from cotizaciones.models import Herramienta

HERRAMIENTAS = [
    "Kaseya 365 Endpoint",
    "Kaseya 365 User",
    "Saas Alert",
    "Datto AV",
    "VSA",
    "Saas Protection",
    "INKY",
    "Cloud Continuity",
    "Datto EDR",
    "Autotask PSA",
    "Datto RMM",
    "Dark Web ID",
    "File Protection Server",
    "File Protection User",
    "Datto Workplace server",
    "Datto Workplace user",
    "Bullphish ID",
    "Compliance GRC",
    "Net Detec Pro",
    "Cyberhawk",
    "Vulscan",
    "SIEM",
    "Datto Continuity for Azure",
    "Vonahi",
    "Secpod Server",
    "Secpod User",
    "Auvik",
    "Auvik telco",
    "Auvik Add-on",
    "Beachhead Secure",
]


class Command(BaseCommand):
    help = "Carga el catálogo inicial de herramientas"

    def handle(self, *args, **kwargs):
        creadas = 0
        for nombre in HERRAMIENTAS:
            obj, creada = Herramienta.objects.get_or_create(nombre=nombre)
            if creada:
                creadas += 1
        self.stdout.write(self.style.SUCCESS(f"Listo. {creadas} herramientas nuevas cargadas."))