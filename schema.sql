-- FitMeal database schema (PostgreSQL 14+). Safe to run more than once.
-- All timestamps are timestamptz (stored as UTC, shown in Africa/Addis_Ababa by the app).

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS staff (
    tg_user_id BIGINT PRIMARY KEY,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('owner', 'kitchen')),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tg_user_id      BIGINT NOT NULL UNIQUE,
    username        TEXT,
    full_name       TEXT,
    phone           TEXT,
    age             INTEGER,
    gender          TEXT,
    allergies       TEXT,
    fitness_goal    TEXT,
    location_hint   TEXT,
    signup_complete BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS addresses (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label        TEXT NOT NULL,
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION,
    address_text TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS categories (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meals (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    meal_code     TEXT NOT NULL UNIQUE,              -- e.g. M-012
    name          TEXT NOT NULL,
    category_id   BIGINT NOT NULL REFERENCES categories(id),
    price_etb     INTEGER NOT NULL CHECK (price_etb >= 0),
    calories      INTEGER NOT NULL,
    protein_g     NUMERIC(6,1) NOT NULL,
    carbs_g       NUMERIC(6,1) NOT NULL,
    fat_g         NUMERIC(6,1) NOT NULL,
    description   TEXT,                               -- shown to customers
    recipe        TEXT,                               -- kitchen only, never shown to customers
    photo_file_id TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    sold_out_on   DATE,                               -- set to a date to mark sold out for that day
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingredients (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    unit     TEXT NOT NULL DEFAULT 'g',
    allergen TEXT                                     -- e.g. dairy, egg, peanut, gluten
);

CREATE TABLE IF NOT EXISTS meal_ingredients (
    meal_id       BIGINT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    ingredient_id BIGINT NOT NULL REFERENCES ingredients(id),
    quantity      NUMERIC(8,2) NOT NULL,
    PRIMARY KEY (meal_id, ingredient_id)
);

CREATE TABLE IF NOT EXISTS payment_accounts (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label          TEXT NOT NULL,                     -- e.g. Telebirr, CBE
    account_number TEXT NOT NULL,
    holder_name    TEXT NOT NULL,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cart_items (
    user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    meal_id  BIGINT NOT NULL REFERENCES meals(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    note     TEXT,
    PRIMARY KEY (user_id, meal_id)
);

-- One row per day, used to build Order IDs like FIT-261030-007
CREATE TABLE IF NOT EXISTS order_counters (
    day         DATE PRIMARY KEY,
    last_number INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code           TEXT NOT NULL UNIQUE,        -- the Order ID customers and kitchen see
    customer_id          BIGINT NOT NULL REFERENCES users(id),
    status               TEXT NOT NULL DEFAULT 'awaiting_payment' CHECK (status IN (
        'awaiting_payment', 'payment_review', 'confirmed', 'preparing', 'ready',
        'out_for_delivery', 'delivered', 'expired', 'payment_denied',
        'cancelled', 'refund_needed', 'refunded')),
    subtotal_etb         INTEGER NOT NULL,
    delivery_fee_etb     INTEGER NOT NULL,
    total_etb            INTEGER NOT NULL,
    dest_latitude        DOUBLE PRECISION,
    dest_longitude       DOUBLE PRECISION,
    dest_text            TEXT,
    dest_maps_url        TEXT,
    receiver_name        TEXT,
    receiver_phone       TEXT,
    delivery_time        TIMESTAMPTZ,                 -- set by the kitchen when payment is approved
    payment_requested_at TIMESTAMPTZ,
    payment_deadline_at  TIMESTAMPTZ,                 -- requested_at + payment window (10 min)
    review_started_at    TIMESTAMPTZ,                 -- when the screenshot arrived (30 min clock)
    last_alert_at        TIMESTAMPTZ,                 -- last reminder or overdue alert to staff
    cancel_reason        TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (dest_text IS NOT NULL OR (dest_latitude IS NOT NULL AND dest_longitude IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS order_items (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    meal_id        BIGINT NOT NULL REFERENCES meals(id),
    meal_code      TEXT NOT NULL,                     -- snapshot at order time
    meal_name      TEXT NOT NULL,                     -- snapshot at order time
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_etb INTEGER NOT NULL,                  -- snapshot at order time
    note           TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id         BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    telegram_file_id TEXT NOT NULL,                   -- the screenshot, stored as a Telegram reference
    submitted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    reviewed_by      BIGINT,                          -- staff Telegram ID
    reviewed_at      TIMESTAMPTZ,
    reason           TEXT,
    allow_resend     BOOLEAN NOT NULL DEFAULT FALSE
);

-- Audit log: who changed what, and when
CREATE TABLE IF NOT EXISTS order_events (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    status       TEXT NOT NULL,
    actor_type   TEXT NOT NULL CHECK (actor_type IN ('customer', 'staff', 'system')),
    actor_tg_id  BIGINT,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refunds (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES orders(id),
    amount_etb INTEGER NOT NULL,
    method     TEXT,
    reference  TEXT,
    note       TEXT,
    logged_by  BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sent_by         BIGINT,
    text            TEXT,
    photo_file_id   TEXT,
    recipient_count INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_order  ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_events_order    ON order_events(order_id);
