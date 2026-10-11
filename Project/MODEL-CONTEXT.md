# Automatic local model context

Qoder no longer applies fixed 2,048/4,096-token contexts. Each fresh model load
reads its installed GGUF metadata and chooses the largest estimated context
that fits available phone RAM without exceeding the model's advertised native
context. It retains two inference slots. Limits can grow when other apps release
memory and shrink when the phone has less available memory. A loaded runtime
keeps its chosen limit until a fresh model load; selecting the same loaded model
does not continually restart it as available RAM fluctuates.

`backend/context_policy.py` accounts for model file size, Q8 K/V cache storage,
attention layers and dimensions, both slots, a 512 MiB compute allowance, and
1 GiB of Android headroom. It includes a 15% KV allowance and 5% model allowance.
Hybrid Qwen3.5 uses its full-attention interval when calculating token KV storage.
This is a memory estimate, not a benchmark proving reliable generation at every
possible context length. Model architecture, compute buffers and Android memory
pressure can affect actual use. Load and inference failures remain errors.

If even 2,048 tokens cannot fit the budget, the model remains installed but is
temporarily unavailable for loading; close other apps and select it again.
The model catalog reports native, planned and active context limits. The loader
records context policy version and migrates old 2K/4K runtimes on their next load.
Extra prompt-cache storage and recurrent context checkpoints are disabled to
avoid additional multi-gigabyte allocations. Batch and microbatch sizes are 512
and 128; K/V quantization remains Q8 rather than changing model quality for size.

Worker prompts use the loaded model's template and tokenizer to reserve space
for the reply. Older complete tool-result pairs are removed only when necessary;
the worker policy, task and latest evidence are retained verbatim. An oversized
essential prompt stops with an explicit context error. The old 8,000-character
history cap and 1,000-character history clipping are removed. This change does
not override the worker's tools, router, policy or verification requirements.
Generation timeouts scale with the actual prompt tokens and reply allowance,
up to four hours. This removes the old three-minute cutoff on long CPU prompts;
the user's Stop control remains available. Processing a large prompt can still
take minutes even when its token count fits the model context.

All changes are in the Termux companion; the attachment APK build 84 remains
compatible and does not need rebuilding. Local inference has no token billing,
but long prompts require memory and CPU time. The 384-token worker reply limit
remains separate from the input context budget.
