from datetime import date
from sqlalchemy.orm import Session
from app.crud.base import CRUDRepository
from app.models.b12_intake import B12Intake


class B12IntakeCRUDRepository(CRUDRepository):
    def get_by_user(self, db: Session, user_id: int) -> list[B12Intake]:
        """
        Get all B12 intakes of a user, most recent first.

        Parameters:
            db (Session): The database session.
            user_id (int): The user ID.

        Returns:
            list[B12Intake]: The user's B12 intakes.
        """
        return db.query(self._model).filter(
            self._model.user_id == user_id
        ).order_by(self._model.intake_date.desc()).all()

    def get_by_user_and_date(
        self, db: Session, user_id: int, intake_date: date
    ) -> B12Intake | None:
        """
        Get a user's B12 intake for a specific day, if any.

        Parameters:
            db (Session): The database session.
            user_id (int): The user ID.
            intake_date (date): The intake day.

        Returns:
            B12Intake | None: The intake for that day, or None.
        """
        return db.query(self._model).filter(
            self._model.user_id == user_id,
            self._model.intake_date == intake_date,
        ).first()


b12_intake_crud = B12IntakeCRUDRepository(model=B12Intake)
