-- init_db.sql — eComBot capstone seed schema
-- Runs once on first PostgreSQL container start.
-- Idempotent: all statements use IF NOT EXISTS / ON CONFLICT DO NOTHING.

-- ── Orders ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    order_id       VARCHAR(20)    PRIMARY KEY,
    customer_name  VARCHAR(100)   NOT NULL,
    product_name   VARCHAR(200)   NOT NULL,
    status         VARCHAR(30)    NOT NULL DEFAULT 'Processing',
    eta            VARCHAR(50)    NOT NULL DEFAULT 'TBD',
    carrier        VARCHAR(50)    NOT NULL DEFAULT 'TBD',
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- ── Products ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    product_id   VARCHAR(20)     PRIMARY KEY,
    name         VARCHAR(200)    NOT NULL,
    category     VARCHAR(50)     NOT NULL,
    price        NUMERIC(10, 2)  NOT NULL,
    stock_qty    INTEGER         NOT NULL DEFAULT 0,
    description  TEXT            NOT NULL DEFAULT '',
    active       BOOLEAN         NOT NULL DEFAULT true
);

-- ── Durable conversation history ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_history (
    id          BIGSERIAL    PRIMARY KEY,
    session_id  VARCHAR(100) NOT NULL,
    user_id     VARCHAR(100) NOT NULL,
    role        VARCHAR(20)  NOT NULL,    -- 'user' | 'model'
    content     TEXT         NOT NULL,
    tool_calls  JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sh_session ON session_history (session_id, created_at);

-- ── Order seed data ───────────────────────────────────────────────────────
INSERT INTO orders (order_id, customer_name, product_name, status, eta, carrier)
VALUES
    ('ORD-001', 'Priya Sharma',  'Noise-Cancelling Headphones XB500',  'Shipped',          '2 Jul 2026',  'BlueDart'),
    ('ORD-002', 'Ravi Patel',    '4K Smart TV 55-inch',                'Processing',       '5 Jul 2026',  'DTDC'),
    ('ORD-003', 'Aisha Mehta',   'Mechanical Keyboard Pro',            'Delivered',        'Already delivered', 'FedEx'),
    ('ORD-004', 'James Liu',     'Wireless Earbuds Ultra',             'Cancelled',        'N/A',         'N/A'),
    ('ORD-005', 'Maria Santos',  'Gaming Mouse RGB',                   'Out for Delivery', 'Today',       'Delhivery'),
    ('ORD-006', 'Kenji Tanaka',  'Portable SSD 1TB',                   'Shipped',          '3 Jul 2026',  'Ecom Express'),
    ('ORD-007', 'Fatima Al-Ali', 'USB-C Hub 7-in-1',                   'Processing',       '6 Jul 2026',  'Amazon Logistics')
ON CONFLICT (order_id) DO NOTHING;

-- ── Product seed data ─────────────────────────────────────────────────────
INSERT INTO products (product_id, name, category, price, stock_qty, description, active)
VALUES
    ('PRD-101', 'Noise-Cancelling Headphones XB500', 'Audio',
     149.99, 42,
     'Over-ear wireless headphones with 30h battery and active noise cancellation.',
     true),

    ('PRD-102', '4K Smart TV 55-inch', 'Television',
     699.00, 0,
     '55-inch 4K UHD Smart TV with built-in streaming apps and HDR10 support. Currently out of stock.',
     true),

    ('PRD-103', 'Mechanical Keyboard Pro', 'Peripherals',
     89.99, 120,
     'Tenkeyless mechanical keyboard with Cherry MX Red switches and RGB backlight.',
     true),

    ('PRD-104', 'Wireless Earbuds Ultra', 'Audio',
     79.99, 65,
     'True wireless earbuds with ANC, 24h total battery, and IPX5 water resistance.',
     true),

    ('PRD-105', 'Gaming Mouse RGB', 'Peripherals',
     49.99, 0,
     'High-precision gaming mouse with 16000 DPI sensor and customizable RGB zones. Discontinued.',
     false),

    ('PRD-106', 'Portable SSD 1TB', 'Storage',
     109.99, 88,
     'USB 3.2 Gen 2 portable SSD with read speeds up to 1050 MB/s. Pocket-sized.',
     true),

    ('PRD-107', 'USB-C Hub 7-in-1', 'Accessories',
     39.99, 200,
     '7-in-1 USB-C hub: 4K HDMI, 100W PD, 2x USB-A, SD card, microSD, USB-C data.',
     true)
ON CONFLICT (product_id) DO NOTHING;
