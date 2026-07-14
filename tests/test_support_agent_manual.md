# eComBot Manual Test Cases
# Day 01–04 capstone scenarios
# Format: Input | Expected tool call | Expected behavior | Observed | Pass/Fail

---

## Scenario 1: Valid order lookup — ORD-001

| Field           | Value                                         |
|-----------------|-----------------------------------------------|
| Input           | `Where is my order ORD-001?`                  |
| Expected tool   | `get_order_status("ORD-001")`                 |
| Expected reply  | Returns status "Shipped", ETA, carrier         |
| Observed        |                                               |
| Pass/Fail       |                                               |

---

## Scenario 2: Not-found order

| Field           | Value                                         |
|-----------------|-----------------------------------------------|
| Input           | `Check order ORD-999`                         |
| Expected tool   | `get_order_status("ORD-999")`                 |
| Expected reply  | Polite not-found message, no invented details |
| Observed        |                                               |
| Pass/Fail       |                                               |

---

## Scenario 3: Invalid order ID format

| Field           | Value                                           |
|-----------------|-------------------------------------------------|
| Input           | `Track order XYZ-100`                           |
| Expected tool   | `get_order_status("XYZ-100")`                   |
| Expected reply  | Polite format error (ORD-XXX expected)          |
| Observed        |                                                 |
| Pass/Fail       |                                                 |

---

## Scenario 4: Multi-turn — name + order + follow-up

| Turn | Input                              | Expected                                         |
|------|------------------------------------|--------------------------------------------------|
| 1    | `Hi, my name is Priya.`            | Agent stores name (customer_name in state)       |
| 2    | `Where is my order ORD-001?`       | Tool called; reply uses "Priya"                  |
| 3    | `What is the carrier?`             | No tool call needed; uses last_order_id in state |
| 4    | `Cancel ORD-001`                   | `cancel_order("ORD-001")` called                 |

| Turn | Observed | Pass/Fail |
|------|----------|-----------|
| 1    |          |           |
| 2    |          |           |
| 3    |          |           |
| 4    |          |           |

---

## Scenario 5: Product lookup

| Field           | Value                                              |
|-----------------|----------------------------------------------------|
| Input           | `Tell me about the 4K Smart TV`                    |
| Expected tool   | `lookup_product("4K Smart TV")`                    |
| Expected reply  | Product details including out-of-stock status      |
| Observed        |                                                    |
| Pass/Fail       |                                                    |

---

## Scenario 6: Cancel already-cancelled order

| Field           | Value                                                        |
|-----------------|--------------------------------------------------------------|
| Input           | `Cancel ORD-004`                                             |
| Expected tool   | `cancel_order("ORD-004")`                                    |
| Expected reply  | Polite message: already cancelled, no changes made           |
| Observed        |                                                              |
| Pass/Fail       |                                                              |

---

## Scenario 7: Out-of-scope request

| Field           | Value                                                   |
|-----------------|---------------------------------------------------------|
| Input           | `Write me a Python function to sort a list`             |
| Expected tool   | None                                                    |
| Expected reply  | Polite refusal, offers e-commerce help instead          |
| Observed        |                                                         |
| Pass/Fail       |                                                         |

---

## Scenario 8: Session restart (Day 04 only)

| Step | Action                                     | Expected                                     |
|------|--------------------------------------------|----------------------------------------------|
| 1    | Run demo with `SESSION_BACKEND=database`   | Session ID printed                           |
| 2    | Ask `Where is ORD-001?`                    | Tool called, order returned                  |
| 3    | Stop the app (Ctrl+C)                      | Process exits                                |
| 4    | Restart with same session ID               | Session state restored from PostgreSQL/Redis |
| 5    | Ask `What was my last order?`              | Replies with ORD-001 from state              |

| Step | Observed | Pass/Fail |
|------|----------|-----------|
| 1    |          |           |
| 2    |          |           |
| 3    |          |           |
| 4    |          |           |
| 5    |          |           |
