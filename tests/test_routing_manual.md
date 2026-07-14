# Day 07 — LiteLLM Routing Manual Tests

Run with: `SESSION_BACKEND=memory python demo.py`

## Expected behaviour

| # | Query | Expected route | Expected model |
|---|-------|----------------|----------------|
| 1 | "What is your return policy?" | fast-faq | gemini-2.5-flash |
| 2 | "Where is my order ORD-001?" | fast-faq | gemini-2.5-flash |
| 3 | "Compare the 4K Smart TV and 8K OLED TV" | deep-support | gemini-2.5-pro |
| 4 | "Recommend the best phone under ₹20,000" | deep-support | gemini-2.5-pro |
| 5 | "How long does shipping take?" | fast-faq | gemini-2.5-flash |
| 6 | "What are the pros and cons of the iPhone 15?" | deep-support | gemini-2.5-pro |

## Routing log format

Each turn prints a `[routing]` line:
```
[routing] success  gemini-2.5-flash (120 ms)
[routing] success  gemini-2.5-pro   (310 ms)
```

## Fallback verification

Set `FAST_MODEL=openrouter/google/bad-model-xyz` in .env and run a FAQ query.
Expected: `[routing] failure  bad-model-xyz ← ModelNotFoundError` then success on BACKUP_MODEL.
