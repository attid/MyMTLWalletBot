from typing import Union
from aiogram import types
import cv2
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


def float2str(f, short: bool = False) -> str:
    if isinstance(f, str):
        if f == 'unlimited':
            return f
        f = float(f)
    if short and f > 0.01:
        s = "%.2f" % f
    else:
        s = "%.8f" % f
        s = s[:-1]
    while len(s) > 1 and s[-1] in ('0', '.'):
        l = s[-1]
        s = s[0:-1]
        if l == '.':
            break
    return s


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
