"""Import-safety tests for the Discord gateway adapter."""

import subprocess
import sys
from textwrap import dedent


class TestDiscordImportSafety:
    def test_module_imports_even_when_discord_dependency_is_missing(self):
        """Probe the fallback in a child interpreter to avoid poisoning imports.

        Re-importing a package after deleting it from ``sys.modules`` mutates
        attributes on each parent package. Pytest restores the module mapping,
        but not those parent attributes, so later tests could receive the
        simulated-missing adapter with ``discord=None``.
        """
        script = dedent(
            """
            import builtins
            import importlib

            original_import = builtins.__import__

            def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "discord" or name.startswith("discord."):
                    raise ImportError("discord unavailable for test")
                return original_import(name, globals, locals, fromlist, level)

            builtins.__import__ = fake_import
            module = importlib.import_module("plugins.platforms.discord.adapter")
            assert module.DISCORD_AVAILABLE is False
            assert module.discord is None
            """
        )

        subprocess.run([sys.executable, "-c", script], check=True)
