"""Multi-module fixture for tracer.py's whole-package selftests.

Deliberately exercises the two things the single-file tracer could not do:
a cross-module call, and a call made on a worker thread (which
`sys.setprofile` alone does not see).
"""
