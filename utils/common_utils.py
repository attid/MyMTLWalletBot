from typing import Union
from aiogram import types
import cv2  # opencv-python


def get_user_id(user_id: Union[types.CallbackQuery, types.Message, int]) -> int:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    return user_id


def decode_qr_code(image_path):
    # Загрузка изображения
    image = cv2.imread(image_path)

    # Инициализация детектора QR-кода
    qr_code_detector = cv2.QRCodeDetector()

    # Распознавание и декодирование QR-кода
    decoded_text, points, _ = qr_code_detector.detectAndDecode(image)

    if points is not None:
        return decoded_text
