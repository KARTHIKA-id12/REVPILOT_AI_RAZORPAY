"""Loads raw merchant data into pandas DataFrames. This is the ONLY layer
that touches the database for analytics — every computation downstream
(metrics, RFM, affinity, opportunity scoring) is a pure function over a
DataFrame, which is what makes them independently unit-testable without a
database."""

import uuid

import pandas as pd
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.models.commerce import Cart, CartItem, Order, OrderItem
from app.models.customers import Customer


def load_orders_df(db: Session, merchant_id: uuid.UUID) -> pd.DataFrame:
    query = (
        db.query(
            Order.id, Order.customer_id, Order.status, Order.subtotal_amount,
            Order.discount_amount, Order.total_amount, Order.created_at, Order.source,
        )
        .filter(Order.merchant_id == merchant_id)
        .statement
    )
    return pd.read_sql(query, db.bind)


def load_order_items_df(db: Session, merchant_id: uuid.UUID) -> pd.DataFrame:
    query = (
        db.query(
            OrderItem.order_id, OrderItem.product_id, OrderItem.quantity,
            OrderItem.unit_price_amount, Order.status, Order.customer_id, Order.created_at,
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.merchant_id == merchant_id)
        .statement
    )
    return pd.read_sql(query, db.bind)


def load_customers_df(db: Session, merchant_id: uuid.UUID) -> pd.DataFrame:
    query = (
        db.query(
            Customer.id, Customer.name, Customer.email, Customer.total_spend,
            Customer.order_count, Customer.first_order_at, Customer.last_order_at,
        )
        .filter(Customer.merchant_id == merchant_id)
        .statement
    )
    return pd.read_sql(query, db.bind)


def load_products_df(db: Session, merchant_id: uuid.UUID) -> pd.DataFrame:
    query = (
        db.query(
            Product.id, Product.sku, Product.name, Product.price_amount,
            Product.stock_qty, Product.stock_status, Product.category_id,
        )
        .filter(Product.merchant_id == merchant_id)
        .statement
    )
    return pd.read_sql(query, db.bind)


def load_carts_df(db: Session, merchant_id: uuid.UUID) -> pd.DataFrame:
    query = (
        db.query(
            Cart.id, Cart.customer_id, Cart.status, Cart.created_at,
            CartItem.product_id, CartItem.quantity, CartItem.unit_price_amount,
        )
        .join(CartItem, CartItem.cart_id == Cart.id)
        .filter(Cart.merchant_id == merchant_id)
        .statement
    )
    return pd.read_sql(query, db.bind)
