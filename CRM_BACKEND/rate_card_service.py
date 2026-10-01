import json
from Database import db_query, db_execute

def init_rate_cards_table():
    """Create product_rate_cards table and seed with initial rate card data if empty."""
    try:
        db_execute("""
        CREATE TABLE IF NOT EXISTS product_rate_cards (
            id SERIAL PRIMARY KEY,
            category VARCHAR(150) NOT NULL,
            size VARCHAR(100) NOT NULL,
            size_normalized VARCHAR(100) NOT NULL,
            gsm_rates JSONB,
            base_weight_kg NUMERIC,
            pieces_per_kg NUMERIC,
            rate_per_kg_high NUMERIC DEFAULT 195,
            rate_per_kg_low NUMERIC DEFAULT 210,
            default_handles VARCHAR(100) DEFAULT 'None',
            default_bag_type VARCHAR(100) DEFAULT 'Square Bottom',
            min_order_qty INTEGER DEFAULT 500,
            stereo_default_price NUMERIC DEFAULT 1770,
            color_addon_rules JSONB,
            gst_rate NUMERIC DEFAULT 5.0,
            tissue_type VARCHAR(50),
            high_rate NUMERIC,
            low_rate NUMERIC,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Check if table already has rows
        count_res = db_query("SELECT COUNT(*) as count FROM product_rate_cards;", fetch_one=True)
        if count_res and count_res.get("count", 0) > 0:
            print("Product rate cards table already initialized with data.")
            return

        print("Seeding product_rate_cards table with initial May 2026 specifications...")

        # 1. Paper Bags with Handle (Square Bottom)
        handle_rates = {
            "8X3X14": {
                "0-500": {"80": 9.00, "90": 10.00, "100": 11.00, "120": 13.00},
                "501-1500": {"80": 5.50, "90": 6.00, "100": 6.50, "120": 8.00},
                "1501+": {"80": 4.80, "90": 5.30, "100": 5.80, "120": 7.30},
            },
            "8X3X12": {
                "0-500": {"80": 8.00, "90": 9.00, "100": 10.00, "120": 12.00},
                "501-1500": {"80": 5.00, "90": 5.50, "100": 6.00, "120": 7.50},
                "1501+": {"80": 4.20, "90": 4.70, "100": 5.20, "120": 6.70},
            },
            "8X3X10": {
                "0-500": {"80": 8.00, "90": 9.00, "100": 10.00, "120": 12.00},
                "501-1500": {"80": 4.40, "90": 4.90, "100": 5.40, "120": 6.90},
                "1501+": {"80": 3.90, "90": 4.40, "100": 4.90, "120": 6.40},
            },
            "8X3X8": {
                "0-500": {"80": 7.00, "90": 8.00, "100": 9.00, "120": 11.00},
                "501-1500": {"80": 4.00, "90": 4.50, "100": 5.00, "120": 6.50},
                "1501+": {"80": 3.60, "90": 4.10, "100": 4.60, "120": 6.10},
            },
            "8X4X10": {
                "0-500": {"80": 8.50, "90": 9.50, "100": 10.50, "120": 12.50},
                "501-1500": {"80": 4.50, "90": 5.00, "100": 5.50, "120": 7.00},
                "1501+": {"80": 4.00, "90": 4.50, "100": 5.00, "120": 6.50},
            },
            "8X4X14": {
                "0-500": {"80": 10.00, "90": 11.00, "100": 12.00, "120": 14.00},
                "501-1500": {"80": 5.70, "90": 6.20, "100": 6.70, "120": 8.20},
                "1501+": {"80": 4.90, "90": 5.40, "100": 5.90, "120": 7.40},
            },
            "8X6X10": {
                "0-500": {"80": 13.00, "90": 14.00, "100": 15.00, "120": 17.00},
                "501-1500": {"80": 5.50, "90": 6.00, "100": 6.50, "120": 8.00},
                "1501+": {"80": 4.50, "90": 5.00, "100": 5.50, "120": 7.00},
            },
            "8X6X16": {
                "0-500": {"80": 14.50, "90": 15.50, "100": 16.50, "120": 18.50},
                "501-1500": {"80": 7.00, "90": 7.50, "100": 8.00, "120": 9.50},
                "1501+": {"80": 6.00, "90": 6.50, "100": 7.00, "120": 8.50},
            },
            "10X4X16": {
                "0-500": {"80": 12.00, "90": 13.00, "100": 14.00, "120": 16.00},
                "501-1500": {"80": 6.50, "90": 7.00, "100": 7.50, "120": 9.00},
                "1501+": {"80": 5.50, "90": 6.00, "100": 6.50, "120": 8.00},
            },
            "10X6X14": {
                "0-500": {"80": 12.00, "90": 13.00, "100": 14.00, "120": 16.00},
                "501-1500": {"80": 6.50, "90": 7.00, "100": 7.50, "120": 9.00},
                "1501+": {"80": 5.50, "90": 6.00, "100": 6.50, "120": 8.00},
            },
            "10X4X14": {
                "0-500": {"80": 11.00, "90": 12.00, "100": 13.00, "120": 15.00},
                "501-1500": {"80": 6.00, "90": 6.50, "100": 7.00, "120": 8.50},
                "1501+": {"80": 5.00, "90": 5.50, "100": 6.00, "120": 7.50},
            },
            "10X4X12": {
                "0-500": {"80": 10.00, "90": 11.00, "100": 12.00, "120": 14.00},
                "501-1500": {"80": 5.50, "90": 6.00, "100": 6.50, "120": 8.00},
                "1501+": {"80": 4.70, "90": 5.20, "100": 5.70, "120": 7.20},
            },
            "10X4X10": {
                "0-500": {"80": 10.00, "90": 11.00, "100": 12.00, "120": 14.00},
                "501-1500": {"80": 5.00, "90": 5.50, "100": 6.00, "120": 7.50},
                "1501+": {"80": 4.30, "90": 4.80, "100": 5.30, "120": 6.80},
            },
            "12X4X16": {
                "0-500": {"80": 13.00, "90": 14.00, "100": 15.00, "120": 17.00},
                "501-1500": {"80": 7.50, "90": 8.00, "100": 8.50, "120": 10.00},
                "1501+": {"80": 6.50, "90": 7.00, "100": 7.50, "120": 9.00},
            },
            "12X4X14": {
                "0-500": {"80": 12.00, "90": 13.00, "100": 14.00, "120": 16.00},
                "501-1500": {"80": 6.50, "90": 7.00, "100": 7.50, "120": 9.00},
                "1501+": {"80": 5.50, "90": 6.00, "100": 6.50, "120": 8.00},
            },
            "12X6X16": {
                "0-500": {"80": 15.00, "90": 16.00, "100": 17.00, "120": 19.00},
                "501-1500": {"80": 8.50, "90": 9.00, "100": 9.50, "120": 11.00},
                "1501+": {"80": 7.00, "90": 7.50, "100": 8.00, "120": 9.50},
            },
            "12X4X12": {
                "0-500": {"80": 12.00, "90": 13.00, "100": 14.00, "120": 16.00},
                "501-1500": {"80": 6.20, "90": 6.70, "100": 7.20, "120": 8.70},
                "1501+": {"80": 5.20, "90": 5.70, "100": 6.20, "120": 7.70},
            },
            "12X4X10": {
                "0-500": {"80": 11.00, "90": 12.00, "100": 13.00, "120": 15.00},
                "501-1500": {"80": 5.90, "90": 6.40, "100": 6.90, "120": 8.40},
                "1501+": {"80": 5.00, "90": 5.50, "100": 6.00, "120": 7.50},
            },
            "14X5X16": {
                "0-500": {"80": 15.00, "90": 16.00, "100": 17.00, "120": 19.00},
                "501-1500": {"80": 8.50, "90": 9.00, "100": 9.50, "120": 11.00},
                "1501+": {"80": 7.00, "90": 7.50, "100": 8.00, "120": 9.50},
            },
            "14X5X14": {
                "0-500": {"80": 14.00, "90": 15.00, "100": 16.00, "120": 18.00},
                "501-1500": {"80": 8.00, "90": 8.50, "100": 9.00, "120": 11.50},
                "1501+": {"80": 6.50, "90": 7.00, "100": 7.50, "120": 9.00},
            },
            "14X5X12": {
                "0-500": {"80": 14.50, "90": 15.50, "100": 16.50, "120": 18.50},
                "501-1500": {"80": 7.00, "90": 7.50, "100": 8.00, "120": 9.50},
                "1501+": {"80": 6.00, "90": 6.50, "100": 7.00, "120": 8.50},
            },
            "14X5X10": {
                "0-500": {"80": 13.00, "90": 14.00, "100": 15.00, "120": 17.00},
                "501-1500": {"80": 6.50, "90": 7.00, "100": 7.50, "120": 9.00},
                "1501+": {"80": 5.70, "90": 6.20, "100": 6.70, "120": 8.20},
            }
        }

        # Weight per kg specifications
        bag_weights = {
            "8X3X14": (0.022, 45),
            "8X3X12": (0.018, 55),
            "8X3X10": (0.015, 66),
            "8X3X8": (0.013, 76),
            "8X4X10": (0.016, 62),
            "8X4X14": (0.020, 50),
            "8X6X10": (0.020, 50),
            "8X6X16": (0.028, 35),
            "10X4X16": (0.027, 37),
            "10X6X14": (0.026, 38),
            "10X4X14": (0.024, 41),
            "10X4X12": (0.021, 47),
            "10X4X10": (0.018, 55),
            "12X4X16": (0.033, 30),
            "12X4X14": (0.030, 33),
            "12X6X16": (0.035, 28),
            "12X4X12": (0.026, 38),
            "12X4X10": (0.023, 43),
            "14X5X16": (0.051, 19),
            "14X5X14": (0.047, 21),
            "14X5X12": (0.041, 24),
            "14X5X10": (0.034, 29),
        }

        for size_str, tiers in handle_rates.items():
            bw, ppk = bag_weights.get(size_str, (0.020, 50))
            db_execute("""
            INSERT INTO product_rate_cards (
                category, size, size_normalized, gsm_rates, base_weight_kg, pieces_per_kg,
                default_handles, default_bag_type, min_order_qty, stereo_default_price, gst_rate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                "Paper Bags with Handle (Square Bottom)",
                size_str,
                size_str,
                json.dumps(tiers),
                bw,
                ppk,
                "Twisted Paper Handle",
                "Square Bottom",
                1500,
                1770,
                5.0
            ))

        # 2. Without Handle Bags (SQ Bottom / V Shape)
        for size_str, (bw, ppk) in bag_weights.items():
            db_execute("""
            INSERT INTO product_rate_cards (
                category, size, size_normalized, base_weight_kg, pieces_per_kg,
                rate_per_kg_high, rate_per_kg_low, default_handles, default_bag_type, min_order_qty, gst_rate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                "Without Handle Bags (SQ Bottom / V Shape)",
                size_str,
                size_str,
                bw,
                ppk,
                195.0,
                210.0,
                "None",
                "Square Bottom",
                300,
                5.0
            ))

        # 3. Medical Paper Pouches
        for size_str, (bw, ppk) in bag_weights.items():
            db_execute("""
            INSERT INTO product_rate_cards (
                category, size, size_normalized, base_weight_kg, pieces_per_kg,
                rate_per_kg_high, rate_per_kg_low, default_handles, default_bag_type, min_order_qty, gst_rate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                "Medical Paper Pouches",
                size_str,
                size_str,
                bw,
                ppk,
                220.0,
                240.0,
                "None",
                "Medical Pouch",
                300,
                18.0
            ))

        # 4. Tissues Rate Card
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
            """, (
                "Tissues",
                size_str,
                norm,
                t_type,
                high,
                low,
                500,
                18.0,
                "None",
                "Tissues"
            ))

        # 5. Toilet Rolls Rate Card
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
            """, (
                "Toilet Rolls",
                size_str,
                size_str,
                price,
                price,
                moq,
                gst,
                "None",
                "Roll"
            ))

        # 6. Sample Set
        db_execute("""
        INSERT INTO product_rate_cards (
            category, size, size_normalized, high_rate, low_rate,
            min_order_qty, gst_rate, default_handles, default_bag_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            "Sample Set (All Sizes)",
            "All Available Sizes",
            "All Available Sizes",
            100.0,
            100.0,
            1,
            5.0,
            "Included",
            "Sample Set"
        ))

        print("Successfully seeded product_rate_cards table with all specifications!")
    except Exception as e:
        print(f"Error initializing product_rate_cards table: {e}")

def get_all_active_rate_cards():
    """Retrieve all active rate card records from PostgreSQL."""
    rows = db_query("""
    SELECT 
        id, category, size, size_normalized, gsm_rates, base_weight_kg,
        pieces_per_kg, rate_per_kg_high, rate_per_kg_low, default_handles,
        default_bag_type, min_order_qty, stereo_default_price, color_addon_rules,
        gst_rate, tissue_type, high_rate, low_rate, is_active, created_at, updated_at
    FROM product_rate_cards
    WHERE is_active = TRUE
    ORDER BY category, id;
    """)
    return rows or []
