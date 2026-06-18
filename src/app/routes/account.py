from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
 
from app.routes.dependencies import get_current_active_user
from app.crud import user_crud
from app.database.db import get_db
from app.log import get_logger
from app.models import User
from app.schemas.user import UserOut, UserUpdateOwn
from app.schemas.auth import EmailChangeRequest
from app.security import get_password_hash, verify_password
from app.services.email import email_service

log = get_logger(__name__)


router = APIRouter()


@router.get("/", response_model=UserOut, status_code=status.HTTP_200_OK)
def fetch_current_active_user(user: User = Depends(get_current_active_user)):
    """
    Fetches the current active user from the database.

    Parameters:
        user (User, optional): The current active user.

    Returns:
        UserOut: The user object fetched from the database.

    Raises:
        HTTPException: If the current active user is not found.
    """

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Current active user not found",
        )
    return user


@router.put("/", response_model=UserOut, status_code=status.HTTP_200_OK)
def update_current_active_user(
    user_update: UserUpdateOwn,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_current_active_user),
):
    """
    Update a current active user.

    Parameters:
        user_update (UserUpdateOwn): The updated user information.
        db (Session, optional): The database session. Defaults to Depends(get_db).
        active_user (User, optional): The current active user.

    Returns:
        UserOut: The updated user information.

    Raises:
        HTTPException: If the user is not found.
        HTTPException: If there is an error updating the user.
    """

    if active_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Current active user not found. Cannot update.",
        )
    try:
        dict_user_update = user_update.model_dump(
            exclude_unset=True
        )  # exclude_unset=True -
        # do not update fields with None
        if 'password' in dict_user_update:
            dict_user_update['password'] = get_password_hash(
                user_update.password)
        user_in = UserUpdateOwn(
            **dict_user_update
        )
        user = user_crud.update(db, active_user, user_in)
    except IntegrityError as e:
        error_message = str(e.orig)
        if "unique constraint" in error_message.lower() and "nickname" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with NICKNAME {user_in.nickname} already exists",
            ) from e
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Data integrity error: {error_message}",
            ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Couldn't update current active user. Error: {str(e)}",
        ) from e
    return user

@router.patch("/email", status_code=status.HTTP_200_OK)
def request_email_change(
    request: EmailChangeRequest,
    db: Session = Depends(get_db),
    active_user: User = Depends(get_current_active_user),
):
    """
    Request an email change for the current user.
 
    Parameters:
        request (EmailChangeRequest): The email change request containing new_email and current_password.
        db (Session): The database session.
        active_user (User): The current active user.
 
    Returns:
        Dict[str, str]: A confirmation message.
 
    Raises:
        HTTPException: If the user is not found.
        HTTPException: If the password is incorrect.
        HTTPException: If the new email is already in use.
        HTTPException: If the confirmation email fails to send.
    """
    if not active_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current active user not found.",
        )
 
    if not verify_password(request.current_password, active_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )
 
    token = user_crud.request_email_change(db, active_user, request.new_email)
 
    if not token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already in use.",
        )
 
    email_sent = email_service.send_email_change_confirmation(
        email=request.new_email,
        token=token,
        user_nickname=active_user.nickname,
    )
 
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send confirmation email. Please try again later.",
        )
 
    return {"detail": "A confirmation email has been sent to your new email address."}
 
 
@router.get("/email/confirm", status_code=status.HTTP_200_OK)
def confirm_email_change(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Confirm an email change using a token.
 
    Parameters:
        token (str): The email change token from the confirmation link.
        db (Session): The database session.
 
    Returns:
        Dict[str, str]: A confirmation message.
 
    Raises:
        HTTPException: If the token is invalid or expired.
    """
    
    user, old_email = user_crud.confirm_email_change(db, token)
 
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email change token.",
        )
 
    if old_email:
        email_service.send_email_change_notification(
            old_email=old_email,
            new_email=user.email,
            user_nickname=user.nickname,
        )
 
    return {"detail": "Your email address has been updated successfully."}