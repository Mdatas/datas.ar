"""Build a tiny but valid llama-architecture GGUF with random weights.

Used by the integration test to prove the full path (install llama.cpp → start
llama-server → /v1/chat/completions) without downloading a real model. The output is
gibberish by design; only the plumbing is under test.

    python tests/make_tiny_gguf.py /tmp/tiny.gguf
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from gguf import GGUFWriter, TokenType

N_EMBD, N_HEAD, N_HEAD_KV, N_FF, N_LAYER, N_CTX = 64, 4, 4, 128, 2, 512
HEAD_DIM = N_EMBD // N_HEAD

CHAT_TEMPLATE = (
    "{% for m in messages %}{{ m['role'] }}: {{ m['content'] }}\n{% endfor %}"
    "{% if add_generation_prompt %}assistant: {% endif %}"
)


def build(path: Path, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    tokens = ["<unk>", "<s>", "</s>"] + [f"<0x{i:02X}>" for i in range(256)] + ["▁hello", "▁world"]
    types = (
        [TokenType.UNKNOWN, TokenType.CONTROL, TokenType.CONTROL]
        + [TokenType.BYTE] * 256
        + [TokenType.NORMAL] * 2
    )
    n_vocab = len(tokens)

    w = GGUFWriter(str(path), "llama")
    w.add_name("datas-tiny-test")
    w.add_context_length(N_CTX)
    w.add_embedding_length(N_EMBD)
    w.add_block_count(N_LAYER)
    w.add_feed_forward_length(N_FF)
    w.add_head_count(N_HEAD)
    w.add_head_count_kv(N_HEAD_KV)
    w.add_rope_dimension_count(HEAD_DIM)
    w.add_layer_norm_rms_eps(1e-5)
    w.add_vocab_size(n_vocab)
    w.add_file_type(0)  # all F32

    w.add_tokenizer_model("llama")
    w.add_tokenizer_pre("default")
    w.add_token_list(tokens)
    w.add_token_scores([0.0] * n_vocab)
    w.add_token_types([int(t) for t in types])
    w.add_bos_token_id(1)
    w.add_eos_token_id(2)
    w.add_unk_token_id(0)
    w.add_add_bos_token(True)
    w.add_chat_template(CHAT_TEMPLATE)

    def rand(*shape):
        return (rng.standard_normal(shape) * 0.02).astype(np.float32)

    w.add_tensor("token_embd.weight", rand(n_vocab, N_EMBD))
    w.add_tensor("output_norm.weight", np.ones(N_EMBD, dtype=np.float32))
    w.add_tensor("output.weight", rand(n_vocab, N_EMBD))
    for i in range(N_LAYER):
        p = f"blk.{i}."
        w.add_tensor(p + "attn_norm.weight", np.ones(N_EMBD, dtype=np.float32))
        w.add_tensor(p + "attn_q.weight", rand(N_EMBD, N_EMBD))
        w.add_tensor(p + "attn_k.weight", rand(N_HEAD_KV * HEAD_DIM, N_EMBD))
        w.add_tensor(p + "attn_v.weight", rand(N_HEAD_KV * HEAD_DIM, N_EMBD))
        w.add_tensor(p + "attn_output.weight", rand(N_EMBD, N_EMBD))
        w.add_tensor(p + "ffn_norm.weight", np.ones(N_EMBD, dtype=np.float32))
        w.add_tensor(p + "ffn_gate.weight", rand(N_FF, N_EMBD))
        w.add_tensor(p + "ffn_up.weight", rand(N_FF, N_EMBD))
        w.add_tensor(p + "ffn_down.weight", rand(N_EMBD, N_FF))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "tiny.gguf")
    print(build(out), out.stat().st_size, "bytes")
