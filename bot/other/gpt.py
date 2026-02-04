import asyncio

import openai as openai
from loguru import logger

from other.config_reader import config

openai_key = config.openai_key.get_secret_value()

async def talk_open_ai_async(msg=None, msg_data=None, user_name=None):
    openai.organization = "org-Iq64OmMI81NWnwcPtn72dc7E"
    openai.api_key = openai_key
    # list models
    # models = openai.Model.list()

    if msg_data:
        messages = msg_data
    else:
        messages = [{"role": "user", "content": msg}]
        if user_name:
            messages[0]["name"] = user_name
    try:
        print('****', messages)
        chat_completion_resp = await openai.ChatCompletion.acreate(model="gpt-3.5-turbo", messages=messages)
        return chat_completion_resp.choices[0].message.content
    except openai.error.APIError as e:
        logger.info(e.code)
        logger.info(e.args)
        return None

async def gpt_check_message(article):
    promt = """"Вы - виртуальный помощник Wallet, Кошелек, специализирующийся на обработке и анализе текстовых команд. 
    Ваша задача - преобразовать команды пользователя в соответствующий JSON формат, который может быть автоматически использован для выполнения различных задач.
    Валюта перевода всегда EURMTL ! Никогда не уточняй валюту.   
    
    Адресная книга:
    {"club": "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB",
    "Anton": "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM59999",}
    
    Пример: переведи 10 eurmtl в клуб
    Твой ответ: {command: "transfer", "amount": 10, "address": "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB"}

    если какого-то параметра не хватает то уточни его, если всего хватает то пришли только json. Никогда не уточняй валюту. 
    """
    messages = [{"role": "system",
                 "content": promt},
                {"role": "user", "content": article}]
    msg = None
    while msg is None:
        msg = await talk_open_ai_async(msg_data=messages)
        if not msg:
            await asyncio.sleep(1)
    return msg

if __name__ == '__main__':
    print(asyncio.run(gpt_check_message('переведи 10 еврмтл в клуб с мемо спасибо за помощь')))