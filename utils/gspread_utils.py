import asyncio
import os
import gspread_asyncio
from google.oauth2.service_account import Credentials

# https://gspread-asyncio.readthedocs.io/en/latest/index.html#


def get_creds():
    key_path = os.path.join(os.path.dirname(__file__), 'mtl-google-doc.json')

    creds = Credentials.from_service_account_file(key_path)
    scoped = creds.with_scopes([
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    return scoped


agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)


async def gs_check_multi(public_key):
    # Open the MTL_assets worksheet
    agc = await agcm.authorize()
    ss = await agc.open("MTL_assets")

    # Check and process the ACCOUNTS worksheet
    ws_accounts = await ss.worksheet("ACCOUNTS")

    # Find the public_key in the 'pub_key' column (which is column 7, assuming the first column is 1)
    data = await ws_accounts.find(str(public_key), in_column=7)

    if data:
        # Get the whole row where the public_key was found
        row = await ws_accounts.row_values(data.row)

        # Check if 'reserv' is part of the 'signers' column in the found row
        # 'signers' column is assumed to be column 6
        if 'reserv' in row[5]:  # Index 5 because list indexing starts at 0
            return True

    # Return False if public_key is not found or if 'reserv' is not in the 'signers' column
    return False


if __name__ == "__main__":
    pass
    a = asyncio.run(gs_check_multi('GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA'))
    print(a)

