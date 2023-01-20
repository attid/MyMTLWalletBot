from aiogram import Router, types, F

router = Router()


@router.message()
async def cmd_delete(message: types.Message):
    await message.delete()
