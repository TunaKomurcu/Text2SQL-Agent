-- Initialize database 'defaultdb' with schema 'defaultschema' and several sample tables
-- This script is executed by Postgres Docker entrypoint on first run

-- Create schema
CREATE SCHEMA IF NOT EXISTS defaultschema;

-- Create product categories (urun_kategorileri)
CREATE TABLE IF NOT EXISTS defaultschema.product_categories (
    category_id SERIAL PRIMARY KEY,
    category_code VARCHAR(50) UNIQUE NOT NULL,
    category_name TEXT NOT NULL,
    description TEXT
);

-- Create products table
CREATE TABLE IF NOT EXISTS defaultschema.products (
    product_id SERIAL PRIMARY KEY,
    product_code VARCHAR(50) UNIQUE NOT NULL,
    product_name TEXT NOT NULL,
    category_id INTEGER REFERENCES defaultschema.product_categories(category_id),
    price NUMERIC(12,2) DEFAULT 0.0,
    stock INTEGER DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

-- Customers
CREATE TABLE IF NOT EXISTS defaultschema.customers (
    customer_id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    city TEXT,
    signup_date DATE
);

-- Orders
CREATE TABLE IF NOT EXISTS defaultschema.orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES defaultschema.customers(customer_id),
    order_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    total_amount NUMERIC(12,2) DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'created'
);

-- Order items
CREATE TABLE IF NOT EXISTS defaultschema.order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES defaultschema.orders(order_id),
    product_id INTEGER REFERENCES defaultschema.products(product_id),
    quantity INTEGER DEFAULT 1,
    unit_price NUMERIC(12,2) DEFAULT 0.0
);

-- Payments
CREATE TABLE IF NOT EXISTS defaultschema.payments (
    payment_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES defaultschema.orders(order_id),
    paid_amount NUMERIC(12,2) NOT NULL,
    paid_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    method VARCHAR(50)
);

-- Example lookups table to emulate free-text columns
CREATE TABLE IF NOT EXISTS defaultschema.addresses (
    address_id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES defaultschema.customers(customer_id),
    address_line TEXT,
    postal_code VARCHAR(20),
    note TEXT
);

-- Populate categories
INSERT INTO defaultschema.product_categories (category_code, category_name, description) VALUES
('CAT-ELEC','Elektronik','Elektronik ürünler, telefon, bilgisayar'),
('CAT-HOME','Ev Eşyaları','Mutfak ve ev malzemeleri'),
('CAT-SPORT','Spor','Spor malzemeleri ve ekipman'),
('CAT-FASHION','Moda','Giyim ve aksesuar');

-- Populate products (20 rows)
INSERT INTO defaultschema.products (product_code, product_name, category_id, price, stock) VALUES
('P1001','Cep Telefonu Model A',1,4999.90,25),
('P1002','Dizüstü Bilgisayar Z',1,12999.00,12),
('P1003','Kablosuz Kulaklık',1,799.50,100),
('P2001','Tencere Seti 6 Parça',2,399.99,40),
('P2002','Mikrodalga Fırın',2,1200.00,10),
('P3001','Koşu Ayakkabısı',3,899.00,50),
('P3002','Fitness Matı',3,149.90,80),
('P4001','Erkek Kot Pantolon',4,299.99,60),
('P4002','Kadın Bluz',4,199.50,90),
('P1004','Tablet 10"',1,3499.00,20),
('P1005','Smartwatch S',1,999.00,45),
('P2003','Bulaşık Makinesi',2,3499.00,5),
('P2004','Kahve Makinesi',2,599.00,30),
('P3003','Dumbbell Seti',3,1299.00,15),
('P4003','Çocuk Spor Takımı',4,249.00,35),
('P1006','Bluetooth Hoparlör',1,249.90,150),
('P1007','Monitör 27"',1,1899.00,22),
('P1008','Harici SSD 1TB',1,1099.00,40),
('P2005','Buzdolabı',2,6999.00,3),
('P3004','Yoga Block',3,49.90,200);

-- Populate customers (10 rows)
INSERT INTO defaultschema.customers (first_name, last_name, email, city, signup_date) VALUES
('Ahmet','Yılmaz','ahmet.yilmaz@example.com','İstanbul','2023-05-10'),
('Ayşe','Demir','ayse.demir@example.com','Ankara','2022-11-02'),
('Mehmet','Kara','mehmet.kara@example.com','İzmir','2024-01-15'),
('Elif','Şahin','elif.sahin@example.com','Bursa','2023-07-20'),
('Murat','Aydın','murat.aydin@example.com','Antalya','2022-09-30'),
('Zeynep','Koç','zeynep.koc@example.com','Adana','2023-12-05'),
('Kerem','Öztürk','kerem.ozturk@example.com','Gaziantep','2021-03-22'),
('Seda','Çelik','seda.celik@example.com','Mersin','2024-04-01'),
('Bora','Arslan','bora.arslan@example.com','Samsun','2023-02-17'),
('Selin','Kılıç','selin.kilic@example.com','Konya','2024-06-12');

-- Create some orders and items
INSERT INTO defaultschema.orders (customer_id, order_date, total_amount, status) VALUES
(1,'2024-11-01 10:15:00',5499.80,'completed'),
(2,'2024-11-05 12:30:00',1899.00,'completed'),
(1,'2024-11-10 09:00:00',1299.90,'created'),
(3,'2024-11-11 14:00:00',3499.00,'completed'),
(5,'2024-11-12 16:45:00',249.00,'cancelled');

INSERT INTO defaultschema.order_items (order_id, product_id, quantity, unit_price) VALUES
(1,1,1,4999.90),
(1,3,1,799.90),
(2,7,1,149.90),
(3,11,1,999.00),
(4,2,1,12999.00),
(5,15,1,249.00);

-- Payments
INSERT INTO defaultschema.payments (order_id, paid_amount, method) VALUES
(1,5499.80,'credit_card'),
(2,1899.00,'paypal'),
(4,3499.00,'bank_transfer');

-- Addresses
INSERT INTO defaultschema.addresses (customer_id, address_line, postal_code, note) VALUES
(1,'İstiklal Cad. No:10, Beyoğlu','34430','İş yeri adresi'),
(2,'Atatürk Bulv. No:5, Çankaya','06000','Ev adresi'),
(3,'Kordonboyu Mah. No:7, Konak','35210','Açık adres'),
(4,'Nilüfer Mh. No:12, Nilüfer','16110','Apartman adı: Gül'),
(5,'Lara Blv. No:2, Muratpaşa','07000','Yazlık adres');

-- Create an index for faster semantic lexicon lookup
CREATE INDEX IF NOT EXISTS idx_products_name ON defaultschema.products USING gin (to_tsvector('turkish', product_name));

-- Done
