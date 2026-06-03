from pydantic import BaseModel


class ProductDistribution(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    active_count: int


class SummaryOut(BaseModel):
    total_active: int
    expiring_soon: int
    issued_today: int
    active_hwids: int
    by_product: list[ProductDistribution]


class RevenuePoint(BaseModel):
    period: str
    count: int


class RevenueOut(BaseModel):
    granularity: str
    points: list[RevenuePoint]
