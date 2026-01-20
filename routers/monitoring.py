from aiogram import Router, types
from aiogram import F
import re

router = Router()

@router.channel_post(F.text.regexp(r'^\s*#mmwb'), F.chat.id == -1002263825546)
async def handle_monitoring_message(message: types.Message):
    text = message.text or message.caption
    if not text:
        return
        
    # Check for  #mmwb #skynet command=ping pattern
    if re.search(r'#mmwb\s+#skynet\s+command=ping', text, re.IGNORECASE):
        await message.answer('#skynet #mmwb command=pong')

def register_handlers(dp, bot):
    dp.include_router(router)
