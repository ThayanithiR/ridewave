from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_role
from app.core.database import get_db
from app.models import Driver, DriverStatus, User, UserRole
from app.schemas import DriverRegisterRequest, DriverResponse, DriverStatusUpdateRequest

router = APIRouter(prefix="/drivers", tags=["Drivers"])


@router.post("/register", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
async def register_driver_profile(
    req: DriverRegisterRequest,
    current_user: User = Depends(require_role(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Driver).where(Driver.user_id == current_user.id)
    existing_driver = (await db.execute(stmt)).scalar_one_or_none()
    if existing_driver:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Driver profile already exists for this user.",
        )

    driver = Driver(
        user_id=current_user.id,
        vehicle_make=req.vehicle_make,
        vehicle_model=req.vehicle_model,
        vehicle_plate=req.vehicle_plate,
        status=DriverStatus.OFFLINE,
    )
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    return driver


@router.get("/me", response_model=DriverResponse)
async def get_my_driver_profile(
    current_user: User = Depends(require_role(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Driver).where(Driver.user_id == current_user.id)
    driver = (await db.execute(stmt)).scalar_one_or_none()
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Driver profile not found."
        )
    return driver


@router.patch("/status", response_model=DriverResponse)
async def update_driver_status(
    req: DriverStatusUpdateRequest,
    current_user: User = Depends(require_role(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Driver).where(Driver.user_id == current_user.id)
    driver = (await db.execute(stmt)).scalar_one_or_none()
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Driver profile not found."
        )

    # Invariant: Cannot manually go ONLINE if currently in an active ride (BUSY)
    if driver.status == DriverStatus.BUSY and req.status != DriverStatus.BUSY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change status while engaged in an active ride.",
        )

    driver.status = req.status
    await db.commit()
    await db.refresh(driver)
    return driver
