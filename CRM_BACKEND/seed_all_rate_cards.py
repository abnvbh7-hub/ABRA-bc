import json
from Database import db_query, db_execute

def seed_complete_database():
    # 1. Tissues
    has_tissues = db_query("SELECT id FROM product_rate_cards WHERE category = 'Tissues' LIMIT 1;", fetch_one=True)
    if not has_tissues:
        tissue_items = [
            ("30×30", "Soft", 27.0, 25.0, 27.0, "18"),
            ("30×27", "Soft", 26.0, 25.0, 26.0, "18"),
            ("27×27", "Soft", 25.0, 23.0, 25.0, "18"),
            ("30×30", "Hard", 26.0, 24.0, 26.0, "18"),
            ("30×27", "Hard", 25.0, 23.0, 25.0, "18"),
            ("27×27", "Hard", 24.0, 22.0, 24.0, "18"),
            ("22×22", "Hard", 22.0, 21.0, 22.0, "18"),
        ]
        for size_str, t_type, high, low, price, gsm in tissue_items:
            norm = size_str.replace("×", "X")
            db_execute("""
            INSERT INTO product_rate_cards (
                category, size, size_normalized, tissue_type, high_rate, low_rate,
                min_order_qty, gst_rate, default_handles, default_bag_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, ("Tissues", size_str, norm, t_type, high, low, 500, 18.0, "None", "Tissues"))
        print("Seeded Tissues.")

    # 2. Toilet Rolls
    has_rolls = db_query("SELECT id FROM product_rate_cards WHERE category = 'Toilet Rolls' LIMIT 1;", fetch_one=True)
    if not has_rolls:
        toilet_roll_items = [
            ("200 gm", 27.0, 18.0, 300),
            ("150 gm", 23.0, 18.0, 300),
            ("100 gm", 19.0, 18.0, 300),
            ("50 gm", 13.0, 18.0, 300),
        ]
        for size_str, price, gst, moq in toilet_roll_items:
            db_execute("""
            INSERT INTO product_rate_cards (
                category, size, size_normalized, high_rate, low_rate,
                min_order_qty, gst_rate, default_handles, default_bag_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, ("Toilet Rolls", size_str, size_str, price, price, moq, gst, "None", "Roll"))
        print("Seeded Toilet Rolls.")

    # 3. Sample Set
    has_samples = db_query("SELECT id FROM product_rate_cards WHERE category = %s LIMIT 1;", ("Sample Set (All Sizes)",), fetch_one=True)
    if not has_samples:
        db_execute("""
        INSERT INTO product_rate_cards (
            category, size, size_normalized, high_rate, low_rate,
            min_order_qty, gst_rate, default_handles, default_bag_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, ("Sample Set (All Sizes)", "All Available Sizes", "All Available Sizes", 100.0, 100.0, 1, 5.0, "Included", "Sample Set"))
        print("Seeded Sample Set.")

    rows = db_query("SELECT category, count(*) FROM product_rate_cards GROUP BY category;")
    print("Categories in DB now:", rows)

if __name__ == "__main__":
    seed_complete_database()
