"""ARQ GEN core package.

The core layer is the most important part of ARQ GEN (spec section 5).
It contains entities, geometry, units, identification, events, commands,
rules, validation, graphs, calculations, audit, versioning and permissions.
No other layer may depend on a different module's internals; everything
goes through public services (spec section 3).
"""

APP_NAME = "ARQ GEN"
APP_VERSION = "3.50.0"
API_VERSION = "1.0"
