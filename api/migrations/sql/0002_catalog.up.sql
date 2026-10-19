-- Sinh tự động từ migrations/versions/0002_catalog.py (upgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

CREATE TABLE customers (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    tax_code    text,
    email       text,
    phone       text,
    address     text,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE carriers (
    id          bigserial PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    name        text NOT NULL,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ports (
    id          bigserial PRIMARY KEY,
    code        text NOT NULL UNIQUE CHECK (code ~ '^[A-Z]{5}$'),
    name        text NOT NULL,
    aliases     text[] NOT NULL DEFAULT '{}',
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE warehouses (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    address     text NOT NULL,
    customer_id bigint REFERENCES customers(id),
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE truckers (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    phone       text,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE trucks (
    id          bigserial PRIMARY KEY,
    trucker_id  bigint NOT NULL REFERENCES truckers(id),
    plate_no    text NOT NULL UNIQUE,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE drivers (
    id          bigserial PRIMARY KEY,
    trucker_id  bigint NOT NULL REFERENCES truckers(id),
    full_name   text NOT NULL,
    phone       text,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_customers_name ON customers USING gin (name gin_trgm_ops);
ALTER TABLE users ADD CONSTRAINT fk_users_customer FOREIGN KEY (customer_id) REFERENCES customers(id);
ALTER TABLE users ADD CONSTRAINT fk_users_driver FOREIGN KEY (driver_id) REFERENCES drivers(id);
