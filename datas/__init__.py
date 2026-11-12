"""Datas.ar — local AI for everyone.

Download, hit run. Datas reads your device, picks the best open-weight model it can
carry without freezing the machine, downloads it, and runs it through llama.cpp.
Later: switch models, plug in an API key, pool several devices, run agents.
"""

__version__ = "0.5.1"
__app_name__ = "Datas.ar"

from datas import nowindow as _nowindow  # noqa: E402

_nowindow.install()  # Windows: programs started by Datas never flash a console window
