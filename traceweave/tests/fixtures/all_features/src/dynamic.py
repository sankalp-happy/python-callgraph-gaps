import importlib
import sys
from flask import Flask
app = Flask(__name__)

HANDLERS = {}

class Meta(type): pass
class WithMeta(metaclass=Meta): pass

class Proxy:
    def __getattr__(self, item):
        return getattr(self._wrapped, item)      # dynamic getattr

@app.route("/x")                                  # registry decorator
def view(): pass

def dispatch(key, payload):
    return HANDLERS[key](payload)                 # subscript call

def load(modname):
    mod = importlib.import_module(modname)        # dynamic import
    cls = getattr(mod, "Handler")                 # LITERAL -> low weight
    dyn = getattr(mod, modname.title())           # dynamic -> high weight
    return cls, dyn

def sneaky(code):
    exec(code, globals())                         # eval_exec + namespace_access
    sys.modules.pop("x", None)                    # sys_modules
