# eComBot v3 — RAG Manual Test Plan

**Day 05 / Day 06 — ChromaDB Grounding and Hallucination Guard Validation**

---

## Prerequisites

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables in `.env`:
   ```
   OPENROUTER_API_KEY=your-key
   SESSION_BACKEND=memory
   VECTOR_BACKEND=disk
   ```

3. *(Day 06 only)* Generate the sample PDF and index it:
   ```bash
   python scripts/create_sample_pdf.py
   python src/rag/embed_catalog.py --reset
   ```

4. *(Day 05 only — JSON-only index)* Build the index without PDF:
   ```bash
   python src/rag/embed_catalog.py --reset
   ```

5. Run the agent:
   ```bash
   SESSION_BACKEND=memory python demo.py
   ```

---

## Test Case 1 — Clean Match (should answer from retrieved context)

**Query:** `What is your return policy?`

**Expected behaviour:**
- Retrieval: Fetches `faq-returns-policy` chunk (or `ecom_faq.pdf` returns section).
- Agent answer: States the 30-day return window, original packaging requirement, and how to contact support.
- Agent does NOT invent timelines beyond what the knowledge base states.
- Source metadata should be visible in debug logs (source_file, section).

**Pass criteria:** Agent answers with knowledge-base content. No invented facts. Score ≥ 0.40.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Test Case 2 — Partial Match (should answer cautiously from closest chunk)

**Query:** `How long do I have to send something back?`

**Expected behaviour:**
- Retrieval: Partial match on the returns policy chunk (no exact "send something back" phrasing in KB).
- Agent answer: References the 30-day return window from the retrieved chunk.
- Agent does not invent additional terms not in the knowledge base.

**Pass criteria:** Agent surfaces the correct return timeline from retrieved evidence. Similarity score between 0.30 and 0.55.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Test Case 3 — Fallback (query not in knowledge base)

**Query:** `What is the best programming language to learn in 2025?`

**Expected behaviour:**
- Retrieval: No relevant chunks found (or all below SIMILARITY_THRESHOLD).
- Agent answer: States it cannot find that information in the current knowledge base and politely redirects to e-commerce topics.
- Agent does NOT guess or invent an answer.

**Pass criteria:** Agent fires fallback message. No hallucinated answer about programming languages.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Test Case 4 — Hallucination Trap (misleading keywords in knowledge base)

**Query:** `Do you offer a lifetime warranty on all products?`

**Expected behaviour:**
- Retrieval: Returns warranty-related chunks — but those chunks state 1-2 year limits, not lifetime.
- Agent answer: Correctly states the actual warranty periods (1-2 years depending on product) from the retrieved context.
- Agent does NOT say "yes, we offer lifetime warranty" just because the word "warranty" matched.

**Pass criteria:** Agent stays faithful to retrieved text. Corrects the false premise politely.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Test Case 5 — Tool Call Still Works (order lookup overrides RAG)

**Query:** `What is the status of my order ORD-001?`

**Expected behaviour:**
- Agent calls `get_order_status` tool (live data), NOT the knowledge base.
- Order status, carrier, and ETA come from the tool response.
- RAG context (if any) does not override tool results.

**Pass criteria:** Tool is called; accurate live order data returned. RAG does not interfere.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Test Case 6 — PDF Metadata Citation (Day 06 only)

**Query:** `What shipping options do you offer?`

**Expected behaviour:**
- Retrieval: Returns a chunk from `ecom_faq.pdf`, shipping section.
- Agent answer: Includes shipping options from the PDF.
- Debug output shows `source_file: ecom_faq.pdf`, `section: Shipping`, `page: 1`.

**Pass criteria:** Answer grounded in PDF content; metadata correctly traced in logs.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Test Case 7 — Empty Collection Fallback

**Procedure:**
1. Delete the ChromaDB persist directory: `rm -rf data/chroma_db`
2. Do NOT run `embed_catalog.py`.
3. Ask: `What is the warranty on the Wireless Earbuds Ultra?`

**Expected behaviour:**
- Collection is empty; retrieval returns [].
- Agent fires fallback: "I don't have that information in our current knowledge base."
- No exception or traceback shown to the user.

**Pass criteria:** Safe fallback, no crash, no fabricated warranty terms.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Test Case 8 — Weak / Misleading Keywords

**Query:** `Tell me about your return policy for software downloads`

**Expected behaviour:**
- Retrieval: May match the returns FAQ chunk; that chunk states digital downloads are non-refundable.
- Agent answer: States that digital downloads are non-refundable, per the knowledge base.
- Agent does NOT make up a refund policy for software.

**Pass criteria:** Accurate non-refundable statement from retrieved context.

**Result:** [ ] Pass  [ ] Fail  
**Notes:**

---

## Debugging Tips

Print retrieved chunks for any query using:
```python
from src.rag.retriever import retrieve
chunks = retrieve("your query here", n_results=3)
for c in chunks:
    print(c["score"], c["metadata"], c["text"][:120])
```

Rebuild the index after editing knowledge files:
```bash
python src/rag/embed_catalog.py --reset
```

Check collection size:
```python
from src.rag.embed_catalog import get_collection
col = get_collection()
print(col.count())
```
