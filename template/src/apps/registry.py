"""The single `Apps` registry that every app module registers on.

Kept in its own module so no app depends on another app's file, and so app
modules and src/apps/__init__.py can all import it without a cycle.
"""
from mcp.server.apps import Apps

apps = Apps()
