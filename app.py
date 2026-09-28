
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DB = Path(__file__).with_name("fulfillment_hub.db")

STATUS_FLOW = {
    "New": "Processed",
    "Processed": "Picking",
    "Picking": "Picked",
    "Picked": "Packed",
    "Packed": "Staged",
    "Staged": "Shipped",
    "Shipped": "Shipped",
}

st.set_page_config(page_title="Fulfillment Hub", page_icon="📦", layout="wide")


def get_conn():
    return sqlite3.connect(DB)


def read_df(query, params=()):
    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params)


def execute(query, params=()):
    with get_conn() as conn:
        conn.execute(query, params)
        conn.commit()


def metric_value(label, value, delta=None):
    st.metric(label, value, delta=delta)


def load_orders():
    df = read_df("""
        SELECT
            o.*,
            CASE
                WHEN o.status <> 'Shipped' AND datetime(o.due_at) < datetime('now','localtime')
                    THEN 'Overdue'
                WHEN o.status <> 'Shipped'
                     AND datetime(o.due_at) <= datetime('now','localtime','+2 hours')
                    THEN 'Due soon'
                ELSE 'On track'
            END AS sla_state
        FROM orders o
        ORDER BY
            CASE WHEN o.priority='Priority' THEN 0 ELSE 1 END,
            datetime(o.due_at)
    """)
    return df


def update_order_status(order_id, new_status):
    execute("UPDATE orders SET status=? WHERE order_id=?", (new_status, order_id))


st.title("📦 Fulfillment Hub")
st.caption("A lightweight control tower for order fulfillment — designed for a small warehouse team.")

# Sidebar navigation
page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Orders", "Picking Queue", "Inventory", "Staging & Shipping", "Issues"]
)
st.sidebar.divider()
st.sidebar.caption("Demo data • SQLite • Streamlit")
if st.sidebar.button("Refresh"):
    st.rerun()

orders_df = load_orders()
inventory_df = read_df("SELECT * FROM inventory ORDER BY product_name")
issues_df = read_df("SELECT * FROM issues ORDER BY datetime(created_at) DESC")

if page == "Dashboard":
    st.subheader("Today at a glance")

    total = len(orders_df)
    priority_open = len(orders_df[(orders_df.priority == "Priority") & (orders_df.status != "Shipped")])
    overdue = len(orders_df[(orders_df.sla_state == "Overdue") & (orders_df.status != "Shipped")])
    staged = len(orders_df[orders_df.status == "Staged"])
    low_stock = len(inventory_df[(inventory_df.main_qty + inventory_df.overflow_qty) <= inventory_df.reorder_level])
    open_issues = len(issues_df[issues_df.status == "Open"])

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    metric_value("Orders", total)
    c2.metric("Priority open", priority_open)
    c3.metric("Overdue", overdue)
    c4.metric("Staged", staged)
    c5.metric("Low stock", low_stock)
    c6.metric("Open issues", open_issues)

    st.divider()

    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("### Orders by status")
        status_counts = orders_df["status"].value_counts().reindex(
            ["New","Processed","Picking","Picked","Packed","Staged","Shipped"], fill_value=0
        )
        st.bar_chart(status_counts)

    with right:
        st.markdown("### Attention needed")
        attention = orders_df[
            ((orders_df["priority"] == "Priority") & (orders_df["status"] != "Shipped")) |
            ((orders_df["sla_state"] == "Overdue") & (orders_df["status"] != "Shipped"))
        ][["order_id","priority","status","due_at","sla_state"]].head(12)
        st.dataframe(attention, use_container_width=True, hide_index=True)

    st.markdown("### Why these controls?")
    st.write(
        "The dashboard surfaces the operational exceptions most likely to cause missed SLAs: "
        "priority orders, overdue orders, staged parcels, stock risk, and unresolved issues. "
        "The team does not need to inspect multiple spreadsheets to discover these problems."
    )

elif page == "Orders":
    st.subheader("Orders")
    f1, f2, f3 = st.columns(3)
    priority_filter = f1.selectbox("Priority", ["All", "Priority", "Regular"])
    status_filter = f2.selectbox("Status", ["All"] + list(STATUS_FLOW.keys())[:-1] + ["Shipped"])
    sla_filter = f3.selectbox("SLA", ["All", "Overdue", "Due soon", "On track"])

    df = orders_df.copy()
    if priority_filter != "All":
        df = df[df.priority == priority_filter]
    if status_filter != "All":
        df = df[df.status == status_filter]
    if sla_filter != "All":
        df = df[df.sla_state == sla_filter]

    st.dataframe(
        df[["order_id","customer","priority","created_at","due_at","status","courier","shipping_cost","sla_state"]],
        use_container_width=True, hide_index=True
    )

    st.markdown("### Advance an order")
    ids = df.order_id.tolist()
    if ids:
        oid = st.selectbox("Order", ids)
        current = df.loc[df.order_id == oid, "status"].iloc[0]
        next_status = STATUS_FLOW.get(current, current)
        st.write(f"Current status: **{current}** → next suggested status: **{next_status}**")
        if st.button(f"Move {oid} to {next_status}", type="primary"):
            update_order_status(oid, next_status)
            st.success(f"{oid} moved to {next_status}.")
            st.rerun()

elif page == "Picking Queue":
    st.subheader("Picking Queue")
    st.caption("Priority orders are deliberately placed first, then orders by due time.")

    picking = orders_df[
        orders_df.status.isin(["Processed", "Picking"])
    ].copy()

    if picking.empty:
        st.success("No orders waiting for picking.")
    else:
        picking["priority_rank"] = picking["priority"].map({"Priority": 0, "Regular": 1})
        picking = picking.sort_values(["priority_rank", "due_at"])

        view = picking[["order_id","customer","priority","due_at","status","sla_state"]]
        st.dataframe(view, use_container_width=True, hide_index=True)

        oid = st.selectbox("Select order to work on", picking.order_id.tolist())
        current = picking.loc[picking.order_id == oid, "status"].iloc[0]

        st.markdown("#### Items to pick")
        lines = read_df("""
            SELECT ol.order_id, ol.product_id, p.product_name, p.sku, ol.qty,
                   i.main_qty, i.overflow_qty
            FROM order_lines ol
            JOIN inventory i ON i.product_id = ol.product_id
            JOIN (
                SELECT product_id, product_name, sku FROM inventory
            ) p ON p.product_id = ol.product_id
            WHERE ol.order_id = ?
        """, (oid,))
        st.dataframe(
            lines[["product_name","sku","qty","main_qty","overflow_qty"]],
            use_container_width=True, hide_index=True
        )

        shortages = lines[lines["main_qty"] < lines["qty"]]
        if not shortages.empty:
            st.warning("Main warehouse stock is insufficient for one or more lines. Transfer stock before packing.")
        if current == "Processed" and st.button("Start picking", type="primary"):
            update_order_status(oid, "Picking")
            st.rerun()

        if current == "Picking" and st.button("Confirm picked", type="primary"):
            # Demo behavior: move status only. Inventory deduction is done at pack time in this simplified flow.
            update_order_status(oid, "Picked")
            st.success(f"{oid} marked as picked.")
            st.rerun()

elif page == "Inventory":
    st.subheader("Inventory")
    inv = inventory_df.copy()
    inv["total_qty"] = inv["main_qty"] + inv["overflow_qty"]
    inv["risk"] = inv.apply(
        lambda r: "Critical" if r.main_qty == 0 and r.overflow_qty == 0
        else ("Transfer needed" if r.main_qty <= 2 and r.overflow_qty > 0
              else ("Low stock" if r.total_qty <= r.reorder_level else "OK")),
        axis=1
    )

    st.dataframe(
        inv[["product_id","product_name","sku","main_qty","overflow_qty","total_qty","reorder_level","risk"]],
        use_container_width=True, hide_index=True
    )

    st.markdown("### Transfer stock to main warehouse")
    product_id = st.selectbox("Product", inv.product_id.tolist())
    row = inv[inv.product_id == product_id].iloc[0]
    qty = st.number_input(
        "Quantity", min_value=1, max_value=max(1, int(row.overflow_qty)), value=1, step=1
    )
    if st.button("Create transfer", type="primary"):
        if row.overflow_qty < qty:
            st.error("Not enough stock in overflow warehouse.")
        else:
            execute(
                "UPDATE inventory SET overflow_qty=overflow_qty-?, main_qty=main_qty+? WHERE product_id=?",
                (qty, qty, product_id)
            )
            st.success(f"Transferred {qty} unit(s) of {row.product_name} to the main warehouse.")
            st.rerun()

    st.info("Design choice: transfers are explicit rather than silently assuming that spreadsheet stock equals physical stock. This makes shortages visible before picking.")

elif page == "Staging & Shipping":
    st.subheader("Staging & Shipping")

    staged = orders_df[orders_df.status.isin(["Packed", "Staged"])].copy()
    if staged.empty:
        st.success("No packed parcels waiting for staging or pickup.")
    else:
        st.dataframe(
            staged[["order_id","customer","priority","status","courier","due_at"]],
            use_container_width=True, hide_index=True
        )

        oid = st.selectbox("Parcel", staged.order_id.tolist())
        status = staged.loc[staged.order_id == oid, "status"].iloc[0]

        if status == "Packed" and st.button("Mark as staged", type="primary"):
            update_order_status(oid, "Staged")
            st.success(f"{oid} is now staged for pickup.")
            st.rerun()

        if status == "Staged" and st.button("Confirm courier pickup", type="primary"):
            update_order_status(oid, "Shipped")
            st.success(f"{oid} handed over to courier.")
            st.rerun()

    st.markdown("### Courier comparison")
    courier_table = pd.DataFrame([
        {"Courier": "BlueDart", "Cost": "₹120", "Pickup": "13:00", "Use when": "Priority / tighter SLA"},
        {"Courier": "Delhivery", "Cost": "₹95", "Pickup": "15:00", "Use when": "Balanced cost + speed"},
        {"Courier": "Shiprocket", "Cost": "₹85", "Pickup": "17:00", "Use when": "Cost sensitive"},
    ])
    st.dataframe(courier_table, use_container_width=True, hide_index=True)

elif page == "Issues":
    st.subheader("Issue Log")
    st.caption("Every exception gets an ownerable record instead of relying on memory or informal messages.")

    st.dataframe(issues_df, use_container_width=True, hide_index=True)

    st.markdown("### Log an issue")
    with st.form("issue_form"):
        order_id = st.text_input("Order ID (optional)")
        issue_type = st.selectbox(
            "Issue type",
            ["Missing stock", "Wrong variant", "Courier pickup missed",
             "Damaged packaging", "Label problem", "Other"]
        )
        severity = st.selectbox("Severity", ["Low", "Medium", "High"])
        description = st.text_area("Description")
        submitted = st.form_submit_button("Create issue", type="primary")

        if submitted:
            existing = read_df("SELECT issue_id FROM issues ORDER BY issue_id DESC LIMIT 1")
            next_num = 1 if existing.empty else int(existing.issue_id.iloc[0].split("-")[1]) + 1
            new_id = f"ISS-{next_num:03d}"
            execute(
                """INSERT INTO issues(issue_id, order_id, issue_type, description, status, severity, created_at)
                   VALUES (?, ?, ?, ?, 'Open', ?, ?)""",
                (new_id, order_id.strip() or None, issue_type, description.strip() or "No description", severity,
                 datetime.now().isoformat(timespec="minutes"))
            )
            st.success(f"{new_id} created.")
            st.rerun()

    open_issues = issues_df[issues_df.status == "Open"]
    if not open_issues.empty:
        st.markdown("### Resolve an issue")
        issue_id = st.selectbox("Issue", open_issues.issue_id.tolist())
        if st.button("Mark resolved"):
            execute("UPDATE issues SET status='Resolved' WHERE issue_id=?", (issue_id,))
            st.success(f"{issue_id} resolved.")
            st.rerun()
