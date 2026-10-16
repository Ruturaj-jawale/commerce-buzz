"""Risk assessment, card network middleware decisioning, and Cross-Rail Decline DNA."""

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CommerceOrder, Organization, Payment, ReversalLink, Storefront
from app.schemas.risk import (
    ChannelRiskMetrics,
    EntityRiskDNA,
    FailedEntitySummary,
    RealTimeRiskEvaluationRequest,
    RealTimeRiskEvaluationResponse,
    RiskAssessmentSummary,
    RiskDecision,
    RiskTier,
    SystemLensProfile,
)


class RiskAssessmentService:
    def _determine_tier(self, score: float, failure_rate: float) -> RiskTier:
        if score >= 75.0 or failure_rate >= 40.0:
            return "CRITICAL"
        if score >= 50.0 or failure_rate >= 20.0:
            return "HIGH"
        if score >= 25.0 or failure_rate >= 10.0:
            return "ELEVATED"
        return "NORMAL"

    def calculate_risk_assessment(
        self,
        db: Session,
        organization: Organization,
        start_date: date | None = None,
        end_date: date | None = None,
        channel: str | None = None,
    ) -> RiskAssessmentSummary:
        stmt = select(Payment).where(Payment.organization_id == organization.id)
        if start_date:
            stmt = stmt.where(Payment.occurred_at >= datetime.combine(start_date, time.min))
        if end_date:
            stmt = stmt.where(Payment.occurred_at <= datetime.combine(end_date, time.max))
        if channel:
            stmt = stmt.where(Payment.channel == channel.upper())

        payments = list(db.scalars(stmt).all())
        total_txns = len(payments)
        total_vol = sum(p.amount for p in payments)
        currency = payments[0].currency if payments else "USD"

        failed_txns = [p for p in payments if p.status == "failed"]
        returned_txns = [p for p in payments if p.status == "returned"]
        succeeded_txns = [p for p in payments if p.status in {"succeeded", "captured", "settled"}]

        failed_count = len(failed_txns)
        returned_count = len(returned_txns)
        total_problem_txns = failed_count + returned_count
        failed_vol = sum(p.amount for p in failed_txns) + sum(p.amount for p in returned_txns)

        overall_fail_rate = (total_problem_txns / total_txns * 100.0) if total_txns > 0 else 0.0

        # Channel breakdown
        channel_buckets: dict[str, dict[str, Any]] = {}
        for p in payments:
            ch = p.channel or "OTHER"
            if ch not in channel_buckets:
                channel_buckets[ch] = {
                    "total": 0,
                    "failed": 0,
                    "returned": 0,
                    "total_vol": 0.0,
                    "failed_vol": 0.0,
                }
            bucket = channel_buckets[ch]
            bucket["total"] += 1
            bucket["total_vol"] += p.amount
            if p.status == "failed":
                bucket["failed"] += 1
                bucket["failed_vol"] += p.amount
            elif p.status == "returned":
                bucket["returned"] += 1
                bucket["failed_vol"] += p.amount

        channel_metrics = []
        highest_risk_channel = "CARD_SWIPE"
        highest_rate = -1.0

        for ch, data in channel_buckets.items():
            tot = data["total"]
            fl = data["failed"] + data["returned"]
            rate = (fl / tot * 100.0) if tot > 0 else 0.0
            if rate > highest_rate and tot >= 3:
                highest_rate = rate
                highest_risk_channel = ch

            channel_metrics.append(
                ChannelRiskMetrics(
                    channel=ch,
                    total_transactions=tot,
                    failed_transactions=data["failed"],
                    returned_transactions=data["returned"],
                    failure_rate_percentage=round(rate, 2),
                    total_volume=round(data["total_vol"], 2),
                    failed_volume=round(data["failed_vol"], 2),
                )
            )

        # Count linked phantom/delayed reversals
        phantom_count = db.scalar(
            select(func.count(ReversalLink.id)).where(ReversalLink.organization_id == organization.id)
        ) or 0

        # Calculate systemic risk score
        score = min(
            100.0,
            (overall_fail_rate * 0.55) + (math.log10(failed_vol + 1.0) * 8.0),
        )
        tier = self._determine_tier(score, overall_fail_rate)

        # Identify top failing entity
        top_entities = self.get_most_failed_entities(db, organization, limit=1)
        top_entity_name = top_entities[0].entity_name if top_entities else None

        return RiskAssessmentSummary(
            total_transactions=total_txns,
            total_volume=round(total_vol, 2),
            successful_transactions=len(succeeded_txns),
            failed_transactions=failed_count,
            returned_transactions=returned_count,
            failed_volume=round(failed_vol, 2),
            overall_failure_rate=round(overall_fail_rate, 2),
            overall_risk_score=round(score, 1),
            risk_tier=tier,
            highest_risk_channel=highest_risk_channel,
            highest_risk_entity=top_entity_name,
            channel_breakdown=channel_metrics,
            phantom_reversals_detected=phantom_count,
            currency=currency,
        )

    def get_most_failed_entities(
        self,
        db: Session,
        organization: Organization,
        limit: int = 20,
        min_failures: int = 1,
        channel: str | None = None,
    ) -> list[FailedEntitySummary]:
        """Calculates 'Most Failed at Which Name' leaderboard across merchants, ATMs, and VPAs."""
        stmt = select(Payment).where(
            Payment.organization_id == organization.id,
            Payment.entity_name.isnot(None),
        )
        if channel:
            stmt = stmt.where(Payment.channel == channel.upper())

        payments = list(db.scalars(stmt).all())
        grouped: dict[str, dict[str, Any]] = {}

        for p in payments:
            name = (p.entity_name or "Unknown Entity").strip()
            if name not in grouped:
                grouped[name] = {
                    "total_attempts": 0,
                    "failed_count": 0,
                    "returned_count": 0,
                    "total_amount": 0.0,
                    "failed_amount": 0.0,
                    "channels": {},
                }
            row = grouped[name]
            row["total_attempts"] += 1
            row["total_amount"] += p.amount
            ch = p.channel or "OTHER"
            row["channels"][ch] = row["channels"].get(ch, 0) + 1

            if p.status == "failed":
                row["failed_count"] += 1
                row["failed_amount"] += p.amount
            elif p.status == "returned":
                row["returned_count"] += 1
                row["failed_amount"] += p.amount

        results: list[FailedEntitySummary] = []
        for name, data in grouped.items():
            tot = data["total_attempts"]
            fl = data["failed_count"]
            rt = data["returned_count"]
            total_failed = fl + rt
            if total_failed < min_failures:
                continue

            fail_rate = (total_failed / tot * 100.0) if tot > 0 else 0.0
            primary_channel = max(data["channels"].items(), key=lambda x: x[1])[0] if data["channels"] else "CARD_SWIPE"

            # Composite Risk Score (0 - 100)
            score = min(
                100.0,
                (fail_rate * 0.5) + (math.log10(data["failed_amount"] + 1.0) * 10.0) + (min(total_failed, 10) * 1.5),
            )
            tier = self._determine_tier(score, fail_rate)

            # Predictive Phantom Reversal Risk (delayed reversal likelihood)
            phantom_prob = round(min(1.0, (rt / total_failed) * 0.8 + (fail_rate / 200.0)), 2) if total_failed > 0 else 0.0

            # Actionable intelligent recommendations
            if tier == "CRITICAL":
                rec = f"Immediate Investigation: High decline velocity on {primary_channel}. Recommend routing restriction or 2FA step-up."
            elif tier == "HIGH":
                rec = f"Elevated Risk: Monitor settlement reversal lag. High propensity for {primary_channel} dispute chargebacks."
            elif tier == "ELEVATED":
                rec = f"Moderate Anomaly: Check merchant terminal ID and interchange decline codes."
            else:
                rec = "Healthy baseline. Occasional standard failure rate."

            results.append(
                FailedEntitySummary(
                    rank=0,
                    entity_name=name,
                    primary_channel=primary_channel,
                    total_attempts=tot,
                    failed_count=fl,
                    returned_count=rt,
                    total_amount=round(data["total_amount"], 2),
                    failed_amount=round(data["failed_amount"], 2),
                    failure_rate_percentage=round(fail_rate, 2),
                    risk_score=round(score, 1),
                    risk_tier=tier,
                    phantom_reversal_risk=phantom_prob,
                    recommendation=rec,
                )
            )

        # Sort descending by risk_score and failed_count
        results.sort(key=lambda x: (x.risk_score, x.failed_count, x.failed_amount), reverse=True)
        for i, item in enumerate(results[:limit], start=1):
            item.rank = i

        return results[:limit]

    def evaluate_realtime_risk(
        self,
        db: Session,
        organization: Organization,
        request: RealTimeRiskEvaluationRequest,
    ) -> RealTimeRiskEvaluationResponse:
        """Inline Card Network Middleware (Mastercard/Visa -> SaaS MCP -> Bank).

        Evaluates incoming transaction risk in real time against historical entity
        decline rates, channel volatility, and velocity spikes.
        """
        entity = request.entity_name.strip()
        channel = request.channel.upper()

        # Check historical behavior of this entity within the organization
        past_payments = list(
            db.scalars(
                select(Payment).where(
                    Payment.organization_id == organization.id,
                    Payment.entity_name == entity,
                ).limit(200)
            ).all()
        )

        hist_fail_rate = 0.0
        risk_factors: list[str] = []
        risk_score = 15.0  # Base safe score

        if past_payments:
            tot = len(past_payments)
            fl = sum(1 for p in past_payments if p.status in {"failed", "returned"})
            hist_fail_rate = (fl / tot * 100.0) if tot > 0 else 0.0

            if hist_fail_rate >= 35.0:
                risk_score += 45.0
                risk_factors.append(f"Entity '{entity}' has critical historical failure rate ({hist_fail_rate:.1f}%)")
            elif hist_fail_rate >= 15.0:
                risk_score += 25.0
                risk_factors.append(f"Entity '{entity}' has elevated historical decline rate ({hist_fail_rate:.1f}%)")

        # Channel risk multiplier (e.g. ATM cash dispenses and POS swipes have higher fraud risk than 3DS)
        if channel == "ATM" and request.amount > 500:
            risk_score += 20.0
            risk_factors.append("High-value ATM cash withdrawal request")
        elif channel == "CARD_SWIPE" and request.country_code and request.country_code != "USA":
            risk_score += 15.0
            risk_factors.append(f"Cross-border physical card swipe ({request.country_code})")

        # Velocity check: count recent attempts on this entity in past 15 minutes
        now = datetime.now(UTC).replace(tzinfo=None)
        recent_count = db.scalar(
            select(func.count(Payment.id)).where(
                Payment.organization_id == organization.id,
                Payment.entity_name == entity,
                Payment.occurred_at >= now - timedelta(minutes=15),
            )
        ) or 0

        if recent_count >= 5:
            risk_score += 35.0
            risk_factors.append(f"High velocity anomaly: {recent_count} attempts detected in past 15 minutes")

        risk_score = min(100.0, max(0.0, risk_score))
        tier = self._determine_tier(risk_score, hist_fail_rate)

        # Network authorization decision
        if risk_score >= 75.0:
            decision: RiskDecision = "DECLINE"
            action = "Network-level pre-authorization decline recommended. High risk of fraud or terminal failure."
        elif risk_score >= 45.0:
            decision = "REVIEW"
            action = "Step-up authentication required (send 2FA / OTP challenge to cardholder)."
        else:
            decision = "APPROVE"
            action = "Approve transaction. Risk parameters within standard safe tolerance."

        return RealTimeRiskEvaluationResponse(
            transaction_ref=request.transaction_ref,
            decision=decision,
            risk_score=round(risk_score, 1),
            risk_tier=tier,
            channel=channel,
            entity_name=entity,
            historical_entity_failure_rate=round(hist_fail_rate, 2),
            risk_factors=risk_factors or ["Standard normal transaction parameters"],
            suggested_action=action,
            evaluated_at=now,
        )

    def get_entity_risk_dna(
        self,
        db: Session,
        organization: Organization,
        entity_name: str,
    ) -> EntityRiskDNA:
        """Innovative Cross-Rail Decline DNA: bridges card network switch data with commerce orders."""
        entity = entity_name.strip()
        payments = list(
            db.scalars(
                select(Payment).where(
                    Payment.organization_id == organization.id,
                    Payment.entity_name == entity,
                )
            ).all()
        )
        if not payments:
            raise HTTPException(status_code=404, detail=f"No transaction history found for entity '{entity}'")

        tot = len(payments)
        fl = sum(1 for p in payments if p.status in {"failed", "returned"})
        fail_rate = (fl / tot * 100.0) if tot > 0 else 0.0

        # Channel vulnerability breakdown
        ch_counts: dict[str, dict[str, int]] = {}
        for p in payments:
            c = p.channel or "OTHER"
            ch_counts.setdefault(c, {"total": 0, "failed": 0})
            ch_counts[c]["total"] += 1
            if p.status in {"failed", "returned"}:
                ch_counts[c]["failed"] += 1

        vulnerabilities = {
            c: round((data["failed"] / data["total"] * 100.0), 2)
            for c, data in ch_counts.items()
        }

        # Correlate with Commerce Orders microservice
        commerce_order_count = db.scalar(
            select(func.count(CommerceOrder.id)).where(
                CommerceOrder.organization_id == organization.id,
                CommerceOrder.order_ref.in_([p.payment_ref for p in payments]),
            )
        ) or 0

        score = min(100.0, (fail_rate * 0.6) + (math.log10(sum(p.amount for p in payments) + 1.0) * 8.0))
        tier = self._determine_tier(score, fail_rate)

        # Detect cadence
        has_returns = any(p.status == "returned" for p in payments)
        cadence = (
            "Asymmetric Delayed Reversals (Settlement Lag: 24-72 hours)"
            if has_returns
            else "Synchronous Switch Declines (Immediate Timeout/Decline)"
        )

        return EntityRiskDNA(
            entity_name=entity,
            profile_status="ACTIVE_SURVEILLANCE" if tier in {"CRITICAL", "HIGH"} else "STABLE",
            composite_risk_score=round(score, 1),
            risk_tier=tier,
            channel_vulnerabilities=vulnerabilities,
            reversal_velocity_cadence=cadence,
            predicted_loss_ratio=round(min(1.0, fail_rate / 100.0), 3),
            connected_commerce_orders_count=commerce_order_count,
            strategic_remediation=(
                f"Cross-rail intelligence indicates {entity} is most vulnerable on {max(vulnerabilities.items(), key=lambda x: x[1])[0]}. "
                "Enable pre-auth tokenization and route through secondary acquiring rail."
                if vulnerabilities
                else "Maintain standard processing parameters."
            ),
        )

    def detect_system_lens(self, db: Session, organization: Organization) -> SystemLensProfile:
        payments = list(db.scalars(select(Payment).where(Payment.organization_id == organization.id)).all())

        bank_channels = {"ATM", "CARD_SWIPE", "UPI", "TRANSFER", "FEE"}
        bank_tx_count = sum(
            1
            for p in payments
            if (p.channel in bank_channels) or (p.reference_no is not None) or (p.raw_narration is not None)
        )

        active_rails = sorted(list({p.channel for p in payments if p.channel and p.channel in bank_channels}))

        reversal_count = (
            db.scalar(select(func.count(ReversalLink.id)).where(ReversalLink.organization_id == organization.id)) or 0
        )
        has_reversals = reversal_count > 0 or any(p.status == "returned" for p in payments)

        commerce_orders_count = (
            db.scalar(select(func.count(CommerceOrder.id)).where(CommerceOrder.organization_id == organization.id))
            or 0
        )

        storefronts_count = (
            db.scalar(select(func.count(Storefront.id)).where(Storefront.organization_id == organization.id)) or 0
        )
        has_storefronts = storefronts_count > 0

        if bank_tx_count > 0 and commerce_orders_count == 0:
            detected_mode = "BANK_NETWORK"
            recommended_lens = "BANK_NETWORK"
            confidence = min(0.98, 0.70 + (min(bank_tx_count, 100) / 100.0) * 0.28)
            rail_str = ", ".join(active_rails) if active_rails else "SWITCH"
            rationale = (
                f"Auto-detected Bank & Card Network Switch persona: {bank_tx_count} bank/card statement transactions "
                f"detected across rails [{rail_str}] with no active e-commerce storefront orders."
            )
        elif commerce_orders_count > 0 and bank_tx_count == 0:
            detected_mode = "COMMERCE"
            recommended_lens = "COMMERCE"
            confidence = min(0.98, 0.70 + (min(commerce_orders_count, 100) / 100.0) * 0.28)
            rationale = (
                f"Auto-detected Commerce Analytics persona: {commerce_orders_count} storefront purchase orders "
                f"and cart checkout events detected with no interbank statement feeds."
            )
        elif bank_tx_count > 0 and commerce_orders_count > 0:
            detected_mode = "HYBRID"
            if bank_tx_count >= commerce_orders_count:
                recommended_lens = "BANK_NETWORK"
                confidence = round(bank_tx_count / (bank_tx_count + commerce_orders_count), 2)
                rationale = (
                    f"Hybrid workspace detected ({bank_tx_count} bank rail transactions vs {commerce_orders_count} commerce orders). "
                    f"Recommending Bank & Card Switch Sentinel as dominant lens."
                )
            else:
                recommended_lens = "COMMERCE"
                confidence = round(commerce_orders_count / (bank_tx_count + commerce_orders_count), 2)
                rationale = (
                    f"Hybrid workspace detected ({commerce_orders_count} commerce orders vs {bank_tx_count} bank switch transactions). "
                    f"Recommending Commerce Analytics as dominant lens."
                )
        else:
            detected_mode = "COMMERCE"
            recommended_lens = "COMMERCE"
            confidence = 0.50
            rationale = "No transactional data ingested yet. Defaulting to Commerce Analytics workspace."

        return SystemLensProfile(
            detected_mode=detected_mode,
            confidence_score=round(confidence, 2),
            recommended_lens=recommended_lens,
            rationale=rationale,
            total_bank_transactions=bank_tx_count,
            total_commerce_orders=commerce_orders_count,
            active_banking_rails=active_rails,
            has_reversals=has_reversals,
            has_storefronts=has_storefronts,
        )

