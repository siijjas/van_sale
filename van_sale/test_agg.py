import frappe

def test_aggregation():
    try:
        data = frappe.get_all(
            "GL Entry",
            fields=["sum(debit) as debit", "sum(credit) as credit"],
            limit=1
        )
        print(f"Aggregation result: {data}")
    except Exception as e:
        print(f"Aggregation failed: {e}")

test_aggregation()
