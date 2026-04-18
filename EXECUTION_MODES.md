# Execution Modes

MarkFlow provides execution profiles for OCR-centric document extraction, independent of any specific LLM vendor.

## Profiles

### auto (default)
Adaptive behavior for mixed document quality.

- Keeps text-layer prioritization when confidence is high
- Uses OCR and optional remote LLM stages only when needed
- Best for heterogeneous corpora

### fast
Throughput-first profile.

- Reduces expensive post-processing
- Prioritizes low-latency routing objective
- Best for large scanned backlogs

### quality
High-assurance OCR profile.

- Enables stricter confidence enforcement
- Activates stronger recovery behavior for low-confidence pages
- Best for regulated or sensitive document workflows

### local
No remote LLM orchestration.

- Restricts to text-layer and local OCR providers
- Preserves offline/private operation
- Best for air-gapped or compliance-heavy environments

### remote
Remote-first strategy.

- Prioritizes OpenAI-compatible remote multimodal models
- Falls back according to routing decision and OCR confidence
- Best for complex layouts and difficult scans

## Routing Objectives

Use `--routing-mode` to control tradeoffs across discovered models:

- `fast`: favors cost/latency
- `balanced`: balances OCR quality, context, cost, and speed
- `high-accuracy-ocr`: strongly prioritizes OCR/document understanding quality

## TUI Integration

Interactive mode (`--tui`) supports:

1. API key input
2. OpenAI-compatible base URL input
3. Dynamic model discovery (`/v1/models`)
4. OCR-aware recommendation with rationale and tradeoffs
5. Routing debug toggle

## Example

```bash
python app.py --mode quality --routing-mode high-accuracy-ocr --input ./docs --output-dir ./out
```
