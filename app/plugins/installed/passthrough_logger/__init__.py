"""
Example plugin: passthrough_logger

A minimal operation node that forwards its input unchanged while logging
basic stats (frame count, point count) to the application logger.

Use this as a copy-paste starting point for new plugins.
"""

# Bump on every behavioural change (semver). Shown in the node palette.
__version__ = "1.0.0"
