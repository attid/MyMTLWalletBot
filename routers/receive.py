import qrcode
from PIL import ImageDraw, Image, ImageFont
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from routers.start_msg import cmd_info_message
from infrastructure.utils.telegram_utils import my_gettext
from other.stellar_tools import stellar_get_user_account

router = Router()
router.message.filter(F.chat.type == "private")


from infrastructure.services.app_context import AppContext

@router.callback_query(F.data == "Receive")
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    
    if not wallet:
        await callback.answer(my_gettext(callback, "wallet_not_found", app_context=app_context), show_alert=True)
        return

    account_id = wallet.public_key
    msg = my_gettext(callback, "my_address", (account_id,), app_context=app_context)
    send_file = f'qr/{account_id}.png'
    create_beautiful_code(send_file, account_id)

    await cmd_info_message(session, callback, msg, send_file=send_file, app_context=app_context)
    await callback.answer()


def create_qr_with_logo(qr_code_text, logo_img):
    # Создание QR-кода
    qr = qrcode.QRCode(
        version=5,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=1
    )
    qr.add_data(qr_code_text)
    qr.make(fit=True)
    qr_code_img = qr.make_image(fill_color=decode_color('5A89B9')).convert('RGB')

    # Размещение логотипа в центре QR-кода
    pos = ((qr_code_img.size[0] - logo_img.size[0]) // 2 + 5, (qr_code_img.size[1] - logo_img.size[1]) // 2)
    qr_code_img.paste(logo_img, pos)

    return qr_code_img


def create_image_with_text(text, font_path='DejaVuSansMono.ttf', font_size=30, image_size=(200, 50)):
    # Создание пустого изображения
    image = Image.new('RGB', image_size, color='white')
    draw = ImageDraw.Draw(image)

    # Загрузка шрифта
    font = ImageFont.truetype(font_path, font_size)

    # Расчет позиции для размещения текста по центру с использованием textbbox
    textbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = textbox[2] - textbox[0], textbox[3] - textbox[1]
    x = (image_size[0] - text_width) / 2
    y = (image_size[1] - text_height) / 2 - 5

    draw.text((x, y), text, font=font, fill=decode_color('C1D9F9'))

    # Размещение рамки
    xy = [0, 0, image_size[0] - 1, image_size[1] - 1]
    draw.rectangle(xy, outline=decode_color('C1D9F9'), width=2)

    return image


def decode_color(color):
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def create_beautiful_code(file_name, address):
    logo_img = create_image_with_text(f'{address[:4]}..{address[-4:]}')
    qr_with_logo_img = create_qr_with_logo(address, logo_img)
    qr_with_logo_img.save(file_name)


if __name__ == '__main__':
    create_beautiful_code('qr_with_logo.png', 'GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI')
    codes = ('GDWZR66DHAHLC4WKEUEDV6G6QOB5XEUQAXSY37MQRMRJEPP5FRGYGXHM',
             'GB7CUEY263TP7DH5QQFZGK3AN64TR5QPUXVS243AQFB3FZMYZSBPUFZJ',
             'GCVSF2B2B6LWO27WYM3PNTB4QJXWR6B7C7MKXYWR6TRSFSKODICDSIGY',
             'GAY3OXIYBKUC3QPVJ6XXZHY3PBOBOSBGZVLTNUNXGJR3WD7YVMNBEXDB',
             'GBXK5S6KOGRRCIFGSPMGUADKE3CABABP5UAXSO4Z77VGL4Y5CGCTQ3XS',
             'GCF4BBEUYSC2E353FNJ63USZOBHBVCP4ORP623F2CE5T7A4UPCG45LAJ',
             'GAZEFASTL4P7A6ERCSHKWDCKBQVGA4R3V5336ILQF4MSALSAH3VMGHIW',
             'GCY5UPKTZKY7RIS3ERMUX26TFKKJAHRZHGV7LUC5PT5I24LYMUMRRPDG',
             'GCU7E7MKN4BPBJTQI4TYVLRKPWYTT2CLAPDKKB72JV7JHDBZDOUROPXE',
             'GDLZOJGRIM5NGW4EO6SLJD7G6LDHJV7L2IO2AGVZ3YB45MRPOBIAOGJA',
             'GAFGSGW4B2LAUCERFLT5NKEQOBMEKXDGPDNXODP7PN4JMWYEBYMEVENT',
             'GATMFFGLVABYICXTVPKNDBNDLWHGGHVUKTGD7ME6HVFQ6V5OAB2IO3OE')

    for code in codes:
        create_beautiful_code(f'{code}.png', code)
