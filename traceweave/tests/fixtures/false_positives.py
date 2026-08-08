import re, typing as t, sys
PAT = re.compile(r"x")
class C:
    @property
    def v(self): return self._v
    @v.setter
    def v(self, x): self._v = x
    @t.overload
    def f(self, a: int) -> int: ...
def g():
    return 1 if "os" in sys.modules else 0
