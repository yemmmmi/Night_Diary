"""Three-tier memory system for diary analysis.

Submodules are imported lazily on first use. Do not add eager imports here —
``working.py`` transitively imports ``context_compressor``, which pulls in
langchain / chromadb and adds ~15s to startup. Callers should import the
specific submodule they need.
"""
