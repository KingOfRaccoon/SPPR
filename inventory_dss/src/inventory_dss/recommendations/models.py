"""Pydantic v2 schemas for replenishment recommendations and batch diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, Field, computed_field, model_validator

from inventory_dss.models.domain import Recommendation, StockStatus, UrgencyLevel


class DecisionRationale(BaseModel):
    """Structured explainable AI (XAI) rationale for a recommendation."""

    status: StockStatus
    urgency: UrgencyLevel
    order_needed: bool
    stock_diagnostic: str
    supplier_selection_reason: str
    capacity_note: str | None = None
    cost_risk_tradeoff: str | None = None
    full_text: str


class StockHealthSummary(BaseModel):
    """Portfolio-level inventory health summary for executive BI KPIs."""

    total_skus: int = Field(..., ge=0)
    critical_skus: list[str] = Field(default_factory=list)
    reorder_skus: list[str] = Field(default_factory=list)
    optimal_skus: list[str] = Field(default_factory=list)
    excess_skus: list[str] = Field(default_factory=list)

    total_on_hand_value_rub: float = Field(default=0.0, ge=0.0)
    total_in_transit_value_rub: float = Field(default=0.0, ge=0.0)
    total_excess_value_rub: float = Field(default=0.0, ge=0.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def critical_percentage(self) -> float:
        return (
            round((len(self.critical_skus) / self.total_skus) * 100.0, 2)
            if self.total_skus > 0
            else 0.0
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reorder_percentage(self) -> float:
        return (
            round((len(self.reorder_skus) / self.total_skus) * 100.0, 2)
            if self.total_skus > 0
            else 0.0
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def optimal_percentage(self) -> float:
        return (
            round((len(self.optimal_skus) / self.total_skus) * 100.0, 2)
            if self.total_skus > 0
            else 0.0
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def excess_percentage(self) -> float:
        return (
            round((len(self.excess_skus) / self.total_skus) * 100.0, 2)
            if self.total_skus > 0
            else 0.0
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def health_score(self) -> float:
        """Overall health index from 0 to 100."""
        if self.total_skus == 0:
            return 100.0
        score = 100.0 - (
            self.critical_percentage * 0.8
            + self.excess_percentage * 0.4
            + self.reorder_percentage * 0.1
        )
        return round(max(0.0, min(100.0, score)), 1)


class BatchSummary(BaseModel):
    """Aggregated portfolio summary of a recommendation batch."""

    total_skus: int = 0
    total_recommended_spend_rub: float = 0.0
    total_orders_needed: int = 0
    total_recommended_units: float = 0.0


class RecommendationBatch(BaseModel):
    """Aggregate replenishment recommendation report with warehouse utilization metrics."""

    batch_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    recommendations: list[Recommendation] = Field(default_factory=list)
    total_skus_evaluated: int = 0
    orders_needed_count: int = 0

    total_recommended_units: float = 0.0
    total_purchase_cost_rub: float = 0.0
    total_volume_m3: float = 0.0
    total_weight_kg: float = 0.0

    warehouse_volume_capacity_m3: float = 0.0
    warehouse_weight_capacity_kg: float = 0.0
    volume_utilization: float = 0.0
    weight_utilization: float = 0.0
    is_capacity_constrained: bool = False
    constrained_skus: list[str] = Field(default_factory=list)
    summary: BatchSummary | None = None

    @model_validator(mode="after")
    def _populate_summary(self) -> Self:
        if self.summary is None:
            total_skus = (
                len(self.recommendations) if self.recommendations else self.total_skus_evaluated
            )
            self.summary = BatchSummary(
                total_skus=total_skus,
                total_recommended_spend_rub=self.total_purchase_cost_rub,
                total_orders_needed=self.orders_needed_count,
                total_recommended_units=self.total_recommended_units,
            )
        return self
