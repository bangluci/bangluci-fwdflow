-- Sinh tự động từ migrations/versions/0010_finance.py (upgrade). KHÔNG sửa tay, KHÔNG chạy trực tiếp:
-- migration chạy bằng Alembic. Tạo lại: python -m scripts.export_sql_migrations

CREATE TABLE charges (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id  bigint NOT NULL REFERENCES shipments(id),
    direction    text NOT NULL CHECK (direction IN ('COST', 'REVENUE')),
    category     text NOT NULL CHECK (category IN ('OCEAN_FREIGHT', 'THC', 'LOCAL_CHARGE', 'TRUCKING', 'DEM', 'DET',
                                                   'DND_COMBINED', 'CUSTOMS', 'LAST_MILE', 'OTHER')),
    amount       bigint NOT NULL CHECK (amount > 0),
    currency     char(3) NOT NULL CHECK (currency IN ('VND', 'USD')),
    fx_rate      numeric(14, 4) NOT NULL,
    amount_vnd   bigint NOT NULL,
    charge_date  date NOT NULL DEFAULT ((now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date),
    note         text,
    created_by   bigint REFERENCES users(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_charges_fx CHECK ((currency = 'VND' AND fx_rate = 1) OR (currency = 'USD' AND fx_rate > 0))
);
CREATE INDEX ix_charges_shipment ON charges (shipment_id);
CREATE INDEX ix_charges_charge_date ON charges (charge_date);
