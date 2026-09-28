# Fulfillment Hub — Take-Home Project

## 1. Problem framing

XYZ's current process is spreadsheet + shared-folder driven. The operational risks are not that data is completely missing; the bigger problem is that information is fragmented and exceptions are easy to miss.

This prototype focuses on five failure modes:

1. **Priority/SLA misses** — priority orders should be visible and sorted to the top of the work queue.
2. **Inventory mismatch** — main-warehouse stock and overflow stock are separated, so a picker can see when a transfer is needed before packing.
3. **Wrong fulfillment status** — one order lifecycle is visible in a single control-tower view.
4. **Staging/pickup failures** — packed parcels move explicitly through staging and courier handoff.
5. **Untracked operational issues** — exceptions are logged with severity and status so they do not disappear in informal conversations.

## 2. Why this design

The warehouse team is experienced but not highly technical, so the interface intentionally uses a small number of screens and very simple actions:

- **Dashboard**: "what needs attention?"
- **Orders**: "where is this order?"
- **Picking Queue**: "what should I pick next?"
- **Inventory**: "can I physically fulfill it?"
- **Staging & Shipping**: "what is waiting for pickup?"
- **Issues**: "what went wrong and is it resolved?"

The prototype does not try to replace an e-commerce platform, courier APIs, accounting, or a full warehouse-management system. It creates a simple operational control layer around fulfillment.

## 3. Workflow

Order lifecycle:

`New → Processed → Picking → Picked → Packed → Staged → Shipped`

The UI only exposes the next logical action for the selected order.

Priority logic:

- Priority orders sort before regular orders.
- Due time is the secondary sort.
- Dashboard highlights overdue and due-soon orders.

Inventory logic:

- Main warehouse is the only shipping location.
- Overflow stock is shown separately.
- A transfer action moves overflow quantity into main stock.
- Low/critical stock is surfaced.

## 4. Sample data

The SQLite database contains:

- 60 sample orders
- 60+ order lines
- 8 sample products
- Main + overflow inventory
- 4 sample issues
- Courier examples with cost and pickup time

All data is fictional.

## 5. Run locally

Python 3.10+ recommended.

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app is local-first and does not require external APIs.

## 6. Demo flow for the interview

A good 5–7 minute walkthrough is:

1. Open Dashboard and point out priority, overdue, staged, stock and issue counts.
2. Open Picking Queue and select a priority order.
3. Show the order's item lines and explain the main-vs-overflow stock check.
4. Go to Inventory and transfer stock from overflow to main.
5. Return to Picking Queue and move the order through picking/picked.
6. Open Staging & Shipping and mark the parcel staged, then confirm courier pickup.
7. Open Issues and create or resolve an exception.

## 7. What I would build next

For a production version, the highest-value next steps would be:

- barcode scanning for product/order verification
- role-based access (office vs warehouse)
- persistent audit log for every status change
- physical location/bin tracking
- automatic alerts for overdue priority orders
- courier API integration for labels and pickup confirmation
- returns and delivery-to-stock workflow
- real inventory reconciliation/cycle counts
- authentication and backup/monitoring
