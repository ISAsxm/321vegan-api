from typing import Annotated, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.routes.dependencies import get_current_active_user_or_client
from app.crud import b12_intake_crud
from app.database.db import get_db
from app.log import get_logger
from app.models import User, ApiClient
from app.schemas.b12_intake import B12IntakeCreate, B12IntakeOut

log = get_logger(__name__)

router = APIRouter(dependencies=[Depends(get_current_active_user_or_client)])


@router.post(
    "/",
    response_model=B12IntakeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_b12_intake(
    intake_create: Annotated[
        B12IntakeCreate,
        Body(
            examples=[
                {
                    "intake_date": "2026-07-13",
                    "frequency": "weekly",
                    "user_id": 1,
                }
            ]
        ),
    ],
    db: Session = Depends(get_db),
    current_user_or_client: User | ApiClient = Depends(
        get_current_active_user_or_client),
):
    """
    Record a B12 intake for a user on a given day.

    A user has at most one intake per day: recording the same day again
    returns 409 so clients can safely retry queued (offline) intakes.

    Parameters:
        intake_create (B12IntakeCreate): The intake data (intake_date,
            frequency, user_id).
        db (Session): The database session.
        current_user_or_client (User | ApiClient): The current active user or API client.

    Returns:
        B12IntakeOut: The created intake.

    Raises:
        HTTPException: 409 if the intake is already recorded for that day.
        HTTPException: 400 if the user does not exist.
    """
    try:
        intake = b12_intake_crud.create(db, intake_create)
    except IntegrityError as e:
        db.rollback()
        error_message = str(e.orig)
        if "uq_b12_intake_user_date" in error_message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"B12 intake already recorded for user {intake_create.user_id} on {intake_create.intake_date}",
            ) from e
        if "foreign key constraint" in error_message.lower() and "user_id" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with id {intake_create.user_id} does not exist",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Data integrity error: {error_message}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Couldn't create B12 intake. Error: {str(e)}",
        ) from e
    return intake


@router.get(
    "/user/{user_id}",
    response_model=List[Optional[B12IntakeOut]],
    status_code=status.HTTP_200_OK,
)
def fetch_b12_intakes_by_user(
    user_id: int, db: Session = Depends(get_db)
) -> List[Optional[B12IntakeOut]]:
    """
    Fetch all B12 intakes of a user, most recent first.

    Parameters:
        user_id (int): The user ID.
        db (Session): The database session.

    Returns:
        List[Optional[B12IntakeOut]]: The user's B12 intakes.
    """
    return b12_intake_crud.get_by_user(db, user_id)
