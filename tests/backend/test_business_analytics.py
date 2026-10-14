from app.schemas.analytics import CommerceEventIngest
from app.schemas.auth import BootstrapRequest
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.storefront_service import StorefrontService
from app.db.database import SessionLocal, init_db
from app.schemas.storefront import StorefrontCreateRequest


def test_business_metrics_use_canonical_line_items_and_customers() -> None:
    init_db()
    db = SessionLocal()
    try:
        suffix = uuid4().hex[:12]
        bootstrapped = AuthService().bootstrap_organization(db, BootstrapRequest(organization_name="Analytics", organization_slug=f"analytics-{suffix}"))
        organization = AuthService().organization_for_key(db, bootstrapped.api_key.key)
        storefront = StorefrontService().connect(
            db,
            organization,
            StorefrontCreateRequest(name="Analytics source", source="custom-commerce", store_url="https://analytics.example.com"),
        )
        analytics = AnalyticsService()
        product_id = f"product-{uuid4()}"
        customer_id = f"customer-{uuid4()}"
        analytics.ingest(
            db,
            organization,
            storefront.id,
            CommerceEventIngest(payload={
                "order_id": "order-analytics-1",
                "revenue": "30.00",
                "currency": "USD",
                "customer_id": customer_id,
                "event_name": "purchase",
                "items": [{"product_id": product_id, "name": "Running Shoe", "price": "15.00", "quantity": 2}],
            }),
        )
        products = analytics.top_products(db, organization)
        product = next(row for row in products if row.product_id == product_id)
        assert product.product_name == "Running Shoe"
        assert product.units_sold == 2
        assert product.revenue == 30.0
        customers = analytics.customer_metrics(db, organization)
        assert customers.customers >= 1
        assert customers.orders >= 1
        assert customers.average_order_value > 0
    finally:
        db.close()
from uuid import uuid4
