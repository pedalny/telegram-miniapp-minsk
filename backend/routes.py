from datetime import datetime, timezone
from typing import Optional
import hashlib
import hmac
import json
import os
from urllib.parse import unquote

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, String

from .database import DB_TYPE, get_db
from .models import AdminAuditLog, Listing, TermsDocument, User
from .schemas import (
    AcceptTermsRequest,
    AdminAuditResponse,
    AdminUserBanRequest,
    AdminUserResponse,
    AdminUserRoleUpdateRequest,
    ComplianceResponse,
    ListingCreate,
    TermsDocumentResponse,
)

load_dotenv()
router = APIRouter()


def verify_telegram_webapp_data(init_data: str) -> Optional[dict]:
    try:
        data_pairs = {}
        for pair in init_data.split("&"):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            data_pairs[key] = unquote(value)

        received_hash = data_pairs.pop("hash", "")
        user_data_str = data_pairs.get("user", "")
        if not user_data_str:
            return None

        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(data_pairs.items())])

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            return None

        secret_key = hmac.new(
            "WebAppData".encode(),
            bot_token.encode(),
            hashlib.sha256,
        ).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if calculated_hash != received_hash:
            return None

        return json.loads(user_data_str)
    except Exception:
        return None


def _allow_local_auth_bypass() -> bool:
    raw = os.getenv("ALLOW_LOCAL_AUTH_BYPASS")
    if raw is not None:
        return raw.lower() in {"1", "true", "yes", "on"}
    return DB_TYPE != "postgresql"


def _superadmin_telegram_id() -> Optional[int]:
    raw = os.getenv("SUPERADMIN_TELEGRAM_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _get_active_terms(db: Session) -> Optional[TermsDocument]:
    return (
        db.query(TermsDocument)
        .filter(TermsDocument.is_active.is_(True))
        .order_by(TermsDocument.created_at.desc(), TermsDocument.id.desc())
        .first()
    )


def _ensure_superadmin_role(user: User, db: Session) -> None:
    superadmin_id = _superadmin_telegram_id()
    if superadmin_id and user.telegram_id == superadmin_id and user.role != "admin":
        user.role = "admin"
        db.commit()
        db.refresh(user)


def _upsert_user_by_telegram(
    db: Session,
    telegram_id: int,
    username: Optional[str] = None,
) -> User:
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif username and user.username != username:
        user.username = username
        db.commit()
        db.refresh(user)

    _ensure_superadmin_role(user, db)
    return user


def _get_or_create_local_user(db: Session) -> User:
    telegram_id = int(os.getenv("LOCAL_TEST_TELEGRAM_ID", "999999999"))
    username = os.getenv("LOCAL_TEST_USERNAME", "local_test")
    return _upsert_user_by_telegram(db, telegram_id=telegram_id, username=username)


def _serialize_compliance(user: User, db: Session) -> dict:
    active_terms = _get_active_terms(db)
    active_version = active_terms.version if active_terms else None
    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "role": user.role,
        "is_banned": user.is_banned,
        "ban_reason": user.ban_reason,
        "accepted_terms_version": user.accepted_terms_version,
        "accepted_terms_at": user.accepted_terms_at,
        "active_terms_version": active_version,
        "is_terms_accepted": bool(active_version and user.accepted_terms_version == active_version),
    }


def _require_not_banned(user: User) -> None:
    if user.is_banned:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "user_banned",
                "message": "Пользователь заблокирован",
                "reason": user.ban_reason,
            },
        )


def _require_terms_accepted(user: User, db: Session) -> None:
    active_terms = _get_active_terms(db)
    if not active_terms:
        return
    if user.accepted_terms_version != active_terms.version:
        raise HTTPException(
            status_code=428,
            detail={
                "code": "terms_not_accepted",
                "required_version": active_terms.version,
                "message": "Необходимо принять условия пользования",
            },
        )


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "admin_required", "message": "Требуются права администратора"},
        )


def _write_admin_audit(
    db: Session,
    admin_user_id: int,
    action: str,
    target_user_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
    log_row = AdminAuditLog(
        admin_user_id=admin_user_id,
        target_user_id=target_user_id,
        action=action,
        details=details,
    )
    db.add(log_row)
    db.commit()


def _get_current_user(
    db: Session,
    init_data: Optional[str],
) -> User:
    if init_data:
        user_data = verify_telegram_webapp_data(init_data)
        if not user_data:
            raise HTTPException(status_code=401, detail="Неверные данные Telegram")

        telegram_id = user_data.get("id")
        username = user_data.get("username")
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Отсутствует telegram_id")
        return _upsert_user_by_telegram(db, telegram_id=telegram_id, username=username)

    if _allow_local_auth_bypass():
        return _get_or_create_local_user(db)

    raise HTTPException(status_code=401, detail="Требуется авторизация Telegram")


def get_current_user(
    init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
) -> User:
    return _get_current_user(db=db, init_data=init_data)


@router.post("/api/auth/telegram")
async def auth_telegram(
    init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user_data = verify_telegram_webapp_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Неверные данные Telegram")

    telegram_id = user_data.get("id")
    username = user_data.get("username")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Отсутствует telegram_id")

    user = _upsert_user_by_telegram(db, telegram_id=telegram_id, username=username)
    payload = _serialize_compliance(user, db)
    return payload


@router.get("/api/me/compliance", response_model=ComplianceResponse)
async def get_me_compliance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _serialize_compliance(user, db)


@router.get("/api/terms/active", response_model=TermsDocumentResponse)
async def get_active_terms(db: Session = Depends(get_db)):
    terms = _get_active_terms(db)
    if not terms:
        raise HTTPException(status_code=404, detail="Активная версия условий не найдена")
    return {
        "version": terms.version,
        "title": terms.title,
        "content": terms.content,
        "created_at": terms.created_at,
    }


@router.post("/api/terms/accept")
async def accept_terms(
    body: AcceptTermsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_not_banned(user)
    terms = _get_active_terms(db)
    if not terms:
        raise HTTPException(status_code=404, detail="Активная версия условий не найдена")
    if body.version != terms.version:
        raise HTTPException(
            status_code=409,
            detail={"code": "terms_version_mismatch", "required_version": terms.version},
        )

    user.accepted_terms_version = terms.version
    user.accepted_terms_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _serialize_compliance(user, db)


@router.get("/api/listings")
async def get_listings(
    db: Session = Depends(get_db),
    type: Optional[str] = None,
    status: str = "active",
):
    query = db.query(Listing).filter(Listing.status == status)
    if type:
        query = query.filter(Listing.type == type)

    listings = query.all()
    result = []
    for listing in listings:
        result.append(
            {
                "id": listing.id,
                "type": listing.type,
                "title": listing.title,
                "description": listing.description,
                "address": listing.address,
                "payment": listing.payment,
                "contacts": listing.contacts,
                "latitude": listing.latitude,
                "longitude": listing.longitude,
                "username": listing.user.username if listing.user else None,
                "created_at": listing.created_at.isoformat() if listing.created_at else None,
            }
        )
    return result


@router.post("/api/listings")
async def create_listing(
    listing: ListingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_not_banned(user)
    _require_terms_accepted(user, db)

    if listing.type not in ["task", "worker"]:
        raise HTTPException(status_code=400, detail="Тип должен быть 'task' или 'worker'")

    db_listing = Listing(
        user_id=user.id,
        type=listing.type,
        title=listing.title,
        description=listing.description,
        address=listing.address,
        payment=listing.payment,
        contacts=listing.contacts,
        latitude=listing.latitude,
        longitude=listing.longitude,
        status="active",
    )
    db.add(db_listing)
    db.commit()
    db.refresh(db_listing)
    return {
        "id": db_listing.id,
        "type": db_listing.type,
        "title": db_listing.title,
        "status": db_listing.status,
    }


@router.get("/api/listings/my")
async def get_my_listings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_not_banned(user)
    _require_terms_accepted(user, db)

    listings = (
        db.query(Listing)
        .filter(Listing.user_id == user.id, Listing.status == "active")
        .all()
    )

    result = []
    for listing in listings:
        result.append(
            {
                "id": listing.id,
                "type": listing.type,
                "title": listing.title,
                "description": listing.description,
                "address": listing.address,
                "payment": listing.payment,
                "contacts": listing.contacts,
                "latitude": listing.latitude,
                "longitude": listing.longitude,
                "created_at": listing.created_at.isoformat() if listing.created_at else None,
            }
        )
    return result


@router.delete("/api/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_not_banned(user)
    _require_terms_accepted(user, db)

    listing = (
        db.query(Listing)
        .filter(Listing.id == listing_id, Listing.user_id == user.id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Объявление не найдено")

    listing.status = "closed"
    db.commit()
    return {"message": "Объявление снято с публикации"}


@router.get("/api/listings/{listing_id}")
async def get_listing(
    listing_id: int,
    db: Session = Depends(get_db),
):
    listing = (
        db.query(Listing)
        .filter(Listing.id == listing_id, Listing.status == "active")
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Объявление не найдено")

    return {
        "id": listing.id,
        "type": listing.type,
        "title": listing.title,
        "description": listing.description,
        "address": listing.address,
        "payment": listing.payment,
        "contacts": listing.contacts,
        "latitude": listing.latitude,
        "longitude": listing.longitude,
        "username": listing.user.username if listing.user else None,
        "created_at": listing.created_at.isoformat() if listing.created_at else None,
    }


@router.get("/api/admin/users")
async def admin_list_users(
    search: Optional[str] = Query(default=None),
    is_banned: Optional[bool] = Query(default=None),
    role: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)

    query = db.query(User)
    if search:
        telegram_search = f"%{search}%"
        query = query.filter(
            (User.username.ilike(f"%{search}%"))
            | (cast(User.telegram_id, String).ilike(telegram_search))
        )
    if is_banned is not None:
        query = query.filter(User.is_banned.is_(is_banned))
    if role:
        query = query.filter(User.role == role)

    total = query.count()
    rows = (
        query.order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        AdminUserResponse(
            id=row.id,
            telegram_id=row.telegram_id,
            username=row.username,
            role=row.role,
            is_banned=row.is_banned,
            ban_reason=row.ban_reason,
            accepted_terms_version=row.accepted_terms_version,
            accepted_terms_at=row.accepted_terms_at,
            created_at=row.created_at,
        ).model_dump()
        for row in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/api/admin/users/{user_id}/ban")
async def admin_ban_user(
    user_id: int,
    body: AdminUserBanRequest,
    admin_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(admin_user)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать самого себя")

    target.is_banned = True
    target.ban_reason = body.reason
    target.banned_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)

    _write_admin_audit(
        db=db,
        admin_user_id=admin_user.id,
        target_user_id=target.id,
        action="ban_user",
        details=body.reason,
    )
    return {"message": "Пользователь заблокирован"}


@router.post("/api/admin/users/{user_id}/unban")
async def admin_unban_user(
    user_id: int,
    admin_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(admin_user)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    target.is_banned = False
    target.ban_reason = None
    target.banned_at = None
    db.commit()
    db.refresh(target)

    _write_admin_audit(
        db=db,
        admin_user_id=admin_user.id,
        target_user_id=target.id,
        action="unban_user",
        details=None,
    )
    return {"message": "Блокировка снята"}


@router.post("/api/admin/users/{user_id}/role")
async def admin_update_role(
    user_id: int,
    body: AdminUserRoleUpdateRequest,
    admin_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(admin_user)
    if body.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Роль должна быть 'user' или 'admin'")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.id == admin_user.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="Нельзя снять роль admin у самого себя")

    target.role = body.role
    db.commit()
    db.refresh(target)

    _write_admin_audit(
        db=db,
        admin_user_id=admin_user.id,
        target_user_id=target.id,
        action="update_role",
        details=body.role,
    )
    return {"message": "Роль обновлена"}


@router.get("/api/admin/audit", response_model=list[AdminAuditResponse])
async def admin_get_audit(
    limit: int = Query(default=100, ge=1, le=500),
    admin_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(admin_user)
    logs = (
        db.query(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        AdminAuditResponse(
            id=log.id,
            admin_user_id=log.admin_user_id,
            target_user_id=log.target_user_id,
            action=log.action,
            details=log.details,
            created_at=log.created_at,
        )
        for log in logs
    ]
