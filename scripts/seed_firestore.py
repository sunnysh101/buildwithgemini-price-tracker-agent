# Seed Firestore database for price-tracker-agent

from google.cloud import firestore

# IMPORTANT: Hardcode project ID string to prevent project number resolution issues on Agent Platform
PROJECT_ID = "qwiklabs-gcp-03-395857593a33"

db = firestore.Client(project=PROJECT_ID)

seed_items = [
    {
        "id": "sony-wh1000xm5",
        "product_name": "Sony WH-1000XM5",
        "target_price": 350.00,
        "current_gross_price": 388.00,
        "preferred_store": "Walmart",
        "min_trust_score": 4.5,
        "in_stock": True,
        "last_checked": "2026-08-13T21:00:00Z",
    },
    {
        "id": "apple-airpods-pro-2",
        "product_name": "Apple AirPods Pro (2nd Gen)",
        "target_price": 190.00,
        "current_gross_price": 249.00,
        "preferred_store": "Amazon",
        "min_trust_score": 4.5,
        "in_stock": True,
        "last_checked": "2026-08-13T21:00:00Z",
    },
    {
        "id": "macbook-air-m3",
        "product_name": "MacBook Air M3",
        "target_price": 999.00,
        "current_gross_price": 1099.00,
        "preferred_store": "Best Buy",
        "min_trust_score": 4.0,
        "in_stock": True,
        "last_checked": "2026-08-13T21:00:00Z",
    },
]


def seed_database():
    print(f"Seeding Firestore collection 'watchlist_items' in project '{PROJECT_ID}'...")
    collection_ref = db.collection("watchlist_items")

    for item in seed_items:
        doc_id = item["id"]
        data = {k: v for k, v in item.items() if k != "id"}
        collection_ref.document(doc_id).set(data)
        print(f"  ✓ Seeded item: {doc_id} ({item['product_name']})")

    print("Firestore seeding complete!")


if __name__ == "__main__":
    seed_database()
