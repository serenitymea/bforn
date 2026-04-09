from telegram import Update
from config import ADMIN_USER_ID, ADMIN_USERNAME


def is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if ADMIN_USER_ID is not None:
        return user.id == ADMIN_USER_ID
    return bool(user.username) and user.username.lower() == ADMIN_USERNAME.lower().lstrip("@")