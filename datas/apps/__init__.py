"""Third-party AI applications: install, start, stop and show — nothing else.

Datas stays neutral: it does not wrap, filter or alter what these programs do. Each recipe in
``apps.json`` (or a user's own file in ``<data>/apps.d/``) says where the program comes from
(a GitHub repository at a pinned tag), how to install it into its own isolated Python
environment and how to start its web interface. `uv <https://github.com/astral-sh/uv>`_ provides
Python itself and the environments, so nothing has to be installed on the computer beforehand.
"""

from datas.apps.runner import AppManager

__all__ = ["AppManager"]
