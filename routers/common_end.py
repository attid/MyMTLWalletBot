from aiogram import Router, types, F
import re
import json

from aiogram.fsm.context import FSMContext

from routers.send import cmd_send_04
from utils.gpt import gpt_check_message

router = Router()


@router.message()
async def cmd_delete(message: types.Message, state: FSMContext):
    if message.from_user.username == "itolstov":
        if len(message.text.split()) > 3:
            gpt_answer = await gpt_check_message(message.text)

            json_match = re.search(r'{.*}', gpt_answer)
            if json_match:
                json_cmd = json.loads(json_match.group())
                # { "command": "transfer", "amount": 10, "address": "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB", "memo": "спасибо за помощь" }
                if json_cmd.get('command') == 'transfer':
                    try:
                        await state.update_data(send_sum=float(json_cmd.get('amount')),
                                                send_asset_code='EURMTL',
                                                send_address=json_cmd.get('address'),
                                                send_asset_issuer='GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'
                                                )
                        #if memo exist add memo
                        if json_cmd.get('memo'):
                            await state.update_data(memo=json_cmd.get('memo'))
                        await cmd_send_04(message, state)
                    except:
                        pass

            else:
                await message.answer(gpt_answer)



    await message.delete()
