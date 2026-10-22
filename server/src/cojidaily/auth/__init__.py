"""Who is asking (pm/decisions/auth-module-separable.md).

Other modules ask only through api.py: the request's Principal, and the dependency that requires
one. They never read auth's tables or the cookie themselves, so this module's inside can later be
replaced by an external identity provider without touching them.
"""
