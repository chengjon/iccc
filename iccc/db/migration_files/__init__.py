"""Migration files directory for database schema changes.

This directory stores individual migration files created with:
    iccc migrate create <name>

The migration system and base classes are in iccc/db/migrations.py

Each migration file follows the naming convention:
    XXX_description.py

Where XXX is a 3-digit version number (001, 002, etc.) and description
is a brief snake_case description of the migration.
"""
