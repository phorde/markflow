"""MarkFlow package.

OCR-first provider-agnostic PDF extraction pipeline with benchmark-driven model routing.

Core architecture layers:
- OCR and extraction pipeline
- Provider-agnostic LLM client abstraction
- Benchmark ingestion and normalization
- OCR-aware model selection and routing
"""

__all__ = [
	"benchmark_ingestion",
	"llm_client",
	"llm_types",
	"model_selection",
	"provider_presets",
	"routing",
]
