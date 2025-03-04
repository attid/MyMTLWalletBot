from typing import Union
from aiogram import types
import cv2  # opencv-python
from pyzbar.pyzbar import decode
from PIL import Image


def get_user_id(user_id: Union[types.CallbackQuery, types.Message, int]) -> int:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    return user_id


def decode_qr_code_cv(image_path):
    image = cv2.imread(image_path)
    qr_code_detector = cv2.QRCodeDetector()
    decoded_text, points, _ = qr_code_detector.detectAndDecode(image)

    if points is not None and decoded_text:
        return decoded_text
    else:
        return None


def decode_qr_code_pyzbar(image_path):
    image = Image.open(image_path)
    decoded_objects = decode(image)
    if decoded_objects:
        return decoded_objects[0].data.decode('utf-8')
    else:
        return None


def decode_qr_code(image_path):
    result = decode_qr_code_cv(image_path)

    if result is None:
        result = decode_qr_code_pyzbar(image_path)

    if result is None:
        return None
    else:
        return result


if __name__ == '__main__':
    pass
