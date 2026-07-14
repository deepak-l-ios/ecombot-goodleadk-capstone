# eComBot Prompt Variant Testing — Day 02
# Compare instruction variants against the same prompts.
# Record what changes in the response when the instruction changes.

---

## How to use this file

Run the same prompt against each instruction variant by temporarily swapping
the `instruction=` value in `support_agent.py` (or run `product_agent.py` /
`sales_agent.py` separately). Record the response for each.

Instruction files:
- `src/agents/support_instructions_v1.txt` — Neutral, professional
- `src/agents/support_instructions_v2.txt` — Warm, friendly
- `src/agents/support_instructions_v3.txt` — Formal, precise

---

## Prompt 1: Greeting

**Input:** `Hi there! Can you help me?`

| Variant | Response summary | Tone observation |
|---------|-----------------|-----------------|
| v1      |                 |                 |
| v2      |                 |                 |
| v3      |                 |                 |

---

## Prompt 2: Order status (no ID)

**Input:** `Where is my order?`

| Variant | Response summary | Asks for order ID? |
|---------|-----------------|-------------------|
| v1      |                 |                   |
| v2      |                 |                   |
| v3      |                 |                   |

---

## Prompt 3: Out-of-scope request

**Input:** `Can you write Python code to sort a list?`

| Variant | Response summary | Redirects to e-commerce? |
|---------|-----------------|--------------------------|
| v1      |                 |                          |
| v2      |                 |                          |
| v3      |                 |                          |

---

## Prompt 4: Unknown live data

**Input:** `What is the current price of the 4K TV?`

| Variant | Response summary | Avoids inventing price? |
|---------|-----------------|------------------------|
| v1      |                 |                        |
| v2      |                 |                        |
| v3      |                 |                        |

---

## Prompt 5: Follow-up (prior context)

**Turn 1 input:** `My name is Priya.`
**Turn 2 input:** `Can you help me with my recent order?`

| Variant | Turn 2 uses name "Priya"? | Asks for order ID? |
|---------|--------------------------|-------------------|
| v1      |                          |                   |
| v2      |                          |                   |
| v3      |                          |                   |

---

## Prompt 6: Empathy (problem order)

**Input:** `I've been waiting 2 weeks for my order and it still hasn't arrived. I'm really frustrated.`

| Variant | Acknowledges frustration? | Offers to look up order? |
|---------|--------------------------|--------------------------|
| v1      |                          |                          |
| v2      |                          |                          |
| v3      |                          |                          |

---

## Observations

| Observation | Detail |
|-------------|--------|
| Best instruction for empathy        |  |
| Best instruction for precision      |  |
| Best instruction for scope control  |  |
| Best overall for eComBot Day 01-02  |  |
