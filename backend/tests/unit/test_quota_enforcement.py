"""Unit tests for the over-quota enforcement job (data-cap lifecycle)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pyrad.packet
from sqlalchemy import select

from app.core.security import encrypt_secret
from app.jobs.quota_enforcement import run_quota_enforcement
from app.models.audit import AuditLog
from app.models.nas import NasDevice
from app.models.plan import Plan
from app.models.radius import RadAcct
from app.models.subscriber import Subscriber
from app.services import disconnect as disconnect_service
from app.services import usage as usage_service
from app.services.usage import month_window


async def _seed_plan(session, *, quota_gb=100, enforce_quota=False, name="Starter") -> Plan:
    plan = Plan(
        name=name,
        radius_group=f"grp-{name.lower()}",
        price=Decimal("9.99"),
        duration_days=30,
        bandwidth_down_mbps=100,
        bandwidth_up_mbps=10,
        quota_gb=quota_gb,
        enforce_quota=enforce_quota,
    )
    session.add(plan)
    return plan


async def _seed_subscriber(session, plan: Plan, username: str) -> Subscriber:
    sub = Subscriber(
        username=username,
        full_name=f"{username} Smith",
        status="active",
        plan=plan,  # relationship so the FK resolves at flush
    )
    session.add(sub)
    return sub


def _seed_session(
    session,
    username: str,
    *,
    in_octets: int,
    out_octets: int = 0,
    stop=None,
    nas: str = "192.168.0.10",
) -> RadAcct:
    # 12h into the current month: always inside the usage report's window
    start = month_window()[0] + timedelta(hours=12)
    row = RadAcct(
        username=username,
        nasipaddress=nas,
        acctstarttime=start,
        acctstoptime=stop,
        acctsessionid=f"ses-{username}",
        acctsessiontime=3600 if stop is None else 3600,
        acctinputoctets=in_octets,
        acctoutputoctets=out_octets,
        framedipaddress="10.0.0.5",
    )
    session.add(row)
    return row


def _seed_nas(session, *, ip: str = "192.168.0.10") -> NasDevice:
    device = NasDevice(
        name=f"nas-{ip}",
        ip_address=ip,
        shortname=f"nas-{ip}",
        nas_type="other",
        secret_encrypted=encrypt_secret("topsecret"),
        is_active=True,
    )
    session.add(device)
    return device


async def _audit_rows(session) -> list[AuditLog]:
    return list((await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all())


def _ack(*_args, **_kwargs) -> int:
    return pyrad.packet.DisconnectACK


async def test_enforces_over_quota_subscriber_with_live_session(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=1, enforce_quota=True)
    sub = await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=2 * 1024**3)  # 2 GiB > 1 GiB quota
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.checked == 1
    assert summary.over_quota == 1
    assert summary.enforced == 1
    assert summary.sessions_disconnected == 1
    assert summary.sessions_failed == 0
    assert summary.skipped_cooldown == 0
    assert summary.skipped_no_sessions == 0

    rows = await _audit_rows(session)
    quota_entry = next(r for r in rows if r.action == "quota_enforced")
    assert quota_entry.admin_id is None
    assert quota_entry.resource == "subscribers"
    assert quota_entry.metadata_ == {
        "username": "heavy",
        "subscriber_id": sub.id,
        "quota_gb": 1,
        "total_gb": 2.0,
        "pct_used": 200.0,
        "sessions_attempted": 1,
        "sessions_disconnected": 1,
        "sessions_failed": 0,
    }
    # the transport-level per-session entry is written too
    disconnect_entry = next(r for r in rows if r.action == "disconnect")
    assert disconnect_entry.metadata_["result"] == "ack"
    assert disconnect_entry.admin_id is None


async def test_skips_subscribers_under_quota(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=100, enforce_quota=True)
    await _seed_subscriber(session, plan, "light")
    _seed_session(session, "light", in_octets=1024**3)  # 1 GiB < 100 GiB
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.checked == 1
    assert summary.over_quota == 0
    assert summary.enforced == 0
    assert await _audit_rows(session) == []


async def test_skips_when_plan_enforcement_disabled(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=1, enforce_quota=False)
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=2 * 1024**3)
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.over_quota == 0
    assert summary.enforced == 0
    assert await _audit_rows(session) == []


async def test_skips_over_quota_without_live_sessions(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=1, enforce_quota=True)
    await _seed_subscriber(session, plan, "heavy")
    # session already closed -> no live session to disconnect
    _seed_session(session, "heavy", in_octets=2 * 1024**3, stop=datetime.now(UTC))
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.over_quota == 1
    assert summary.skipped_no_sessions == 1
    assert summary.enforced == 0
    assert await _audit_rows(session) == []


async def test_skips_within_cooldown_window(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=1, enforce_quota=True)
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=2 * 1024**3)
    _seed_nas(session)
    session.add(
        AuditLog(
            admin_id=None,
            action="quota_enforced",
            resource="subscribers",
            metadata_={"username": "heavy"},
            created_at=(datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None),
        )
    )
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.over_quota == 1
    assert summary.skipped_cooldown == 1
    assert summary.enforced == 0
    # only the pre-seeded entry — no new audit, no disconnect
    rows = await _audit_rows(session)
    assert len(rows) == 1


async def test_cooldown_expired_re_enforces(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=1, enforce_quota=True)
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=2 * 1024**3)
    _seed_nas(session)
    session.add(
        AuditLog(
            admin_id=None,
            action="quota_enforced",
            resource="subscribers",
            metadata_={"username": "heavy"},
            created_at=(datetime.now(UTC) - timedelta(days=2)).replace(tzinfo=None),
        )
    )
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.skipped_cooldown == 0
    assert summary.enforced == 1
    assert summary.sessions_disconnected == 1


async def test_tolerates_disconnect_failure_and_still_audits(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=1, enforce_quota=True)
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=2 * 1024**3)
    # no NAS registered -> disconnect_service raises ConflictError
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.enforced == 1
    assert summary.sessions_failed == 1
    assert summary.sessions_disconnected == 0
    rows = await _audit_rows(session)
    quota_entry = next(r for r in rows if r.action == "quota_enforced")
    assert quota_entry.metadata_["sessions_failed"] == 1
    assert quota_entry.metadata_["sessions_disconnected"] == 0


async def test_multiple_live_sessions_all_disconnected(session, monkeypatch):
    plan = await _seed_plan(session, quota_gb=1, enforce_quota=True)
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=2 * 1024**3, nas="192.168.0.10")
    _seed_session(session, "heavy", in_octets=1024**3, nas="192.168.0.11")
    _seed_nas(session, ip="192.168.0.10")
    _seed_nas(session, ip="192.168.0.11")
    await session.commit()
    monkeypatch.setattr(disconnect_service, "send_disconnect_request", _ack)

    summary = await run_quota_enforcement(session)

    assert summary.enforced == 1
    assert summary.sessions_disconnected == 2
    assert summary.sessions_failed == 0


def test_build_scheduler_registers_quota_job():
    """The app scheduler carries the quota job on an interval trigger."""
    from app.jobs.invoice_generation import build_scheduler

    scheduler = build_scheduler()
    jobs = {job.id: str(job.trigger) for job in scheduler.get_jobs()}
    assert "quota-enforcement" in jobs
    # interval trigger string looks like "interval[0:00:05]" — not a cron
    assert "interval" in jobs["quota-enforcement"]


async def test_usage_report_carries_enforce_quota_flag(session):
    plan = await _seed_plan(session, quota_gb=100, enforce_quota=True)
    await _seed_subscriber(session, plan, "bob")
    await session.commit()

    (row,) = await usage_service.get_usage_report(session)
    assert row.enforce_quota is True
