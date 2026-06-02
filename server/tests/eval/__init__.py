"""Offline evaluation package (RAG retrieval + generation quality).

Importable helpers (``judge``, ``rubric``) live here; runnable eval suites live
in subpackages (``rag``, ``generation``) and are gated behind the ``eval`` marker
so CI and the default test run skip them.
"""
