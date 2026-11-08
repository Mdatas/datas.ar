"""Pool mode: several devices, one model.

Built on llama.cpp's RPC backend (``ggml-rpc-server`` workers + ``llama-server --rpc``):
weights and KV cache are split across local and remote devices in proportion to their
memory. Workers are found on the LAN with mDNS/DNS-SD (zeroconf) under
``_datas-rpc._tcp.local.``, or listed by hand.

Facts to design around (see docs/POOLING.md):
- Memory is additive, speed is not: every token crosses the network once per boundary.
- All nodes must run the same llama.cpp build (RPC protocol version). Datas pins the tag.
- The RPC protocol is unauthenticated: use it on a trusted LAN or over a VPN only.
"""

from datas.pool.discovery import Node, advertise, discover  # noqa: F401
