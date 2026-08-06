"""Service for managing employee hour balances (back, vacation, sick) with audit trail."""
from sqlalchemy.orm import Session
from app.models.hour_balance import HourBalance, HourTransaction


def get_balance(db: Session, employee_id: str, type: str) -> float:
    """Get current balance for a specific hour type."""
    row = db.query(HourBalance).filter(
        HourBalance.employee_id == employee_id,
        HourBalance.type == type,
    ).first()
    return float(row.balance) if row else 0.0


def get_all_balances(db: Session, employee_id: str) -> dict:
    """Get all hour balances for an employee."""
    types = ["back_hours", "vacation_hours", "sick_hours"]
    return {t: get_balance(db, employee_id, t) for t in types}


def add_hours(
    db: Session,
    employee_id: str,
    type: str,
    amount: float,
    input_by: str,
    input_by_name: str,
    reason: str | None = None,
    pay_period_id: int | None = None,
) -> dict:
    """Add hours to an employee's balance. Creates/updates balance + logs transaction."""
    if type not in ("back_hours", "vacation_hours", "sick_hours"):
        raise ValueError(f"Invalid hour type: {type}")

    # Update balance
    row = db.query(HourBalance).filter(
        HourBalance.employee_id == employee_id,
        HourBalance.type == type,
    ).first()
    if row:
        row.balance = float(row.balance) + amount
    else:
        row = HourBalance(
            employee_id=employee_id,
            type=type,
            balance=amount,
        )
        db.add(row)

    # Log transaction
    txn = HourTransaction(
        employee_id=employee_id,
        type=type,
        amount=amount,
        action="added",
        reason=reason,
        input_by=input_by,
        input_by_name=input_by_name,
        pay_period_id=pay_period_id,
    )
    db.add(txn)
    db.commit()
    db.refresh(row)

    return {
        "employee_id": employee_id,
        "type": type,
        "amount_added": amount,
        "new_balance": float(row.balance),
        "transaction_id": txn.id,
    }


def deduct_hours(
    db: Session,
    employee_id: str,
    type: str,
    amount: float,
    input_by: str,
    input_by_name: str,
    reason: str | None = None,
    time_off_request_id: int | None = None,
) -> dict:
    """Deduct hours from an employee's balance (e.g., when time-off is approved)."""
    if type not in ("back_hours", "vacation_hours", "sick_hours"):
        raise ValueError(f"Invalid hour type: {type}")

    current = get_balance(db, employee_id, type)
    if current < amount:
        raise ValueError(f"Insufficient {type} balance: have {current}, need {amount}")

    # Update balance
    row = db.query(HourBalance).filter(
        HourBalance.employee_id == employee_id,
        HourBalance.type == type,
    ).first()
    if row:
        row.balance = float(row.balance) - amount
    else:
        # No balance record = 0 balance, can't deduct
        raise ValueError(f"No {type} balance to deduct from")

    # Log transaction
    txn = HourTransaction(
        employee_id=employee_id,
        type=type,
        amount=-amount,
        action="deducted",
        reason=reason,
        input_by=input_by,
        input_by_name=input_by_name,
        time_off_request_id=time_off_request_id,
    )
    db.add(txn)
    db.commit()
    db.refresh(row)

    return {
        "employee_id": employee_id,
        "type": type,
        "amount_deducted": amount,
        "new_balance": float(row.balance),
        "transaction_id": txn.id,
    }


def get_transaction_history(db: Session, employee_id: str) -> list[dict]:
    """Get full transaction history for an employee."""
    txns = db.query(HourTransaction).filter(
        HourTransaction.employee_id == employee_id,
    ).order_by(HourTransaction.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "type": t.type,
            "amount": float(t.amount),
            "action": t.action,
            "reason": t.reason,
            "input_by_name": t.input_by_name,
            "time_off_request_id": t.time_off_request_id,
            "pay_period_id": t.pay_period_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in txns
    ]
