"""justregqa — one engine, two rulebooks (KR / HK). Citation-first regulatory Q&A."""
from .answer import Answer, RegQA, render
from .corpus import Clause, list_packs, load_pack

__all__ = ["Answer", "RegQA", "render", "Clause", "list_packs", "load_pack"]
__version__ = "0.1.0"
