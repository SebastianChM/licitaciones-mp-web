# Licitaciones MP Web

Plataforma web para descubrimiento, filtrado y gestión de licitaciones públicas de
[Mercado Público](https://www.mercadopublico.cl) (Chile), construida con Django 5.2 LTS
y Django REST Framework.

Es la **evolución web** de [Licitaciones_MP](https://github.com/SebastianChM/Licitaciones_MP),
un pipeline ETL de escritorio que reduce ~12.000 licitaciones diarias a las ~300 relevantes
por equipo. Esta versión reemplaza los archivos Excel por una base de datos relacional, la
configuración por planilla por el Django Admin, y el reporte estático por una API REST.

> 🚧 **En desarrollo.** Ver [PLAN.md](PLAN.md) para la arquitectura completa y el estado
> de los milestones. Las decisiones técnicas se registran en [docs/decisiones.md](docs/decisiones.md).

## Arranque rápido

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # completar valores
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Calidad

```bash
ruff check . && ruff format --check .   # lint y formato
coverage run -m pytest && coverage report  # tests con gate de cobertura 85%
```

## Stack

Django 5.2 LTS · Django REST Framework · django-filter · pydantic-settings ·
pytest-django · factory-boy · ruff · SQLite (dev) / PostgreSQL-ready (prod)
