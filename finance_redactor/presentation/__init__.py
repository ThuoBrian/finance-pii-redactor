"""Presentation layer: the local web API and the built React interface.

``api`` holds the FastAPI routers, ``jobs`` the in-memory store for uploads,
``security`` the request checks, and ``presenters`` turn domain results into
the tables and wording the interface shows. ``static`` is the built bundle
(source in ``frontend/``).
"""
