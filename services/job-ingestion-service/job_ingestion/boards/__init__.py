"""Ingestion for providers shaped as one board per tenant.

A tenant-board provider answers one slug with every posting that tenant has.
Everything that varies between such providers is carried by a `BoardProvider`
value; everything that does not is implemented once here.

This package exports nothing from its root on purpose. `registry` imports the
providers and the providers import `provider`, so a root that imported the
registry would import itself.
"""
